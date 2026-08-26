"""Logica de business a auth-service.

Separată de routing (`app/routers/auth.py`, care doar validează input-ul
și deleagă aici) și de modele (`app/models.py`, care doar definește
DTO-urile). Acest modul e singurul care atinge `db.users` direct și
singurul care cheamă alte servicii (accounts-service, la provisioning).
"""

import asyncio
import logging
import secrets
from datetime import datetime, timedelta, timezone

import httpx
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status

from app import webauthn_service
from app.config import settings
from app.database import get_database
from app.email_service import send_verification_email
from app.login_events import get_recent_login_events, record_login_attempt
from app.models import ChangePasswordRequest, UserLogin, UserRegister
from app.security import create_access_token, decode_access_token, hash_password, verify_password

logger = logging.getLogger("auth-service")


async def _provision_bank_account(user_id: str) -> None:
    """Cere accounts-service să creeze automat cont RON + IBAN + card virtual.

    MVP sincron, apelat imediat după crearea userului. Dacă accounts-service
    nu răspunde sau eșuează, userul RĂMÂNE creat (autentificarea nu
    depinde de accounts-service) — dar nu va avea încă un cont bancar.
    Nu există (încă) un mecanism automat de reîncercare; e o limitare
    documentată explicit (vezi README și raportul final), acceptabilă
    pentru acest MVP demo. Într-un sistem real s-ar folosi un
    outbox/saga pattern cu retry.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{settings.accounts_service_url}/internal/accounts/provision",
                json={"user_id": user_id},
            )
            response.raise_for_status()
        logger.info("auth-service: cont bancar provizionat pentru user_id=%s", user_id)
    except httpx.HTTPError as exc:
        logger.error(
            "auth-service: PROVIZIONAREA CONTULUI BANCAR A EȘUAT pentru user_id=%s (%s). "
            "Userul a fost creat cu succes, dar NU are încă un cont bancar.",
            user_id,
            exc,
        )


def _generate_verification_code() -> str:
    """Cod numeric de 6 cifre — `secrets.randbelow`, nu `random`, fiindcă
    ajunge într-un flux de securitate (verificare identitate cont)."""
    return f"{secrets.randbelow(1_000_000):06d}"


async def register_user(payload: UserRegister) -> dict:
    db = get_database()

    existing = await db.users.find_one({"email": payload.email})
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Există deja un cont cu acest email.")

    user_doc = {
        "first_name": payload.first_name,
        "last_name": payload.last_name,
        "email": payload.email,
        "phone_number": payload.phone_number,
        # Doar hash-ul ajunge în baza de date — parola în clar nu e
        # niciodată salvată sau logată.
        "password_hash": hash_password(payload.password),
        "created_at": datetime.now(timezone.utc),
        "is_active": True,
        # UserRegister nu are câmp "role" — un client nu poate NICIODATĂ
        # cere rolul "staff" prin înregistrare publică. Singura cale spre
        # role="staff" e scripts/create_staff_user.py, direct în Mongo.
        "role": "customer",
        # Onboarding: userul pornește neverificat pe ambele fronturi —
        # vezi send_verification_code / verify_email_code mai jos și
        # mark_identity_verified (apelat de verification-service).
        "email_verified": False,
        "identity_verified": False,
        "email_verification_code": None,
        "email_verification_expires_at": None,
    }
    result = await db.users.insert_one(user_doc)
    user_id = str(result.inserted_id)
    logger.info("auth-service: cont nou creat (user_id=%s)", user_id)

    await _provision_bank_account(user_id)
    await send_verification_code(user_id)

    return await db.users.find_one({"_id": result.inserted_id})


def _send_verification_email_background(email: str, first_name: str, code: str) -> None:
    """Trimite emailul FĂRĂ să blocheze cererea curentă (nici event loop-ul
    pentru alte cereri) — SMTP-ul e o bibliotecă sincronă (smtplib), iar un
    server lent/inaccesibil (ex. blocat de un firewall de rețea) poate să
    dureze mult peste orice timeout rezonabil de cerere HTTP. `create_task`
    pornește trimiterea într-un thread separat și NU e niciodată așteptat —
    register/resend răspund imediat, indiferent cât durează SMTP-ul.
    Excepțiile sunt deja prinse în email_service.py, nu ajung aici."""
    asyncio.create_task(asyncio.to_thread(send_verification_email, email, first_name, code))


async def send_verification_code(user_id: str) -> None:
    """Generează un cod nou de verificare email și îl trimite (sau îl
    logează, în development — vezi email_service.py). Apelat la register
    ȘI la reîncercare explicită din UI ("Retrimite codul")."""
    db = get_database()
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilizatorul nu există.")

    code = _generate_verification_code()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.email_verification_code_ttl_minutes)
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"email_verification_code": code, "email_verification_expires_at": expires_at}},
    )
    _send_verification_email_background(user["email"], user["first_name"], code)


async def verify_email_code(user_id: str, code: str) -> None:
    db = get_database()
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilizatorul nu există.")

    if user.get("email_verified"):
        return

    if settings.email_verification_test_code and secrets.compare_digest(
        code, settings.email_verification_test_code
    ):
        await db.users.update_one(
            {"_id": user["_id"]},
            {"$set": {"email_verified": True, "email_verification_code": None, "email_verification_expires_at": None}},
        )
        logger.info("auth-service: email verificat cu codul de test (user_id=%s)", user_id)
        return

    stored_code = user.get("email_verification_code")
    expires_at = user.get("email_verification_expires_at")
    if not stored_code or not expires_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cere mai întâi un cod de verificare.")

    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Codul a expirat. Cere unul nou.")

    if not secrets.compare_digest(stored_code, code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cod incorect.")

    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"email_verified": True, "email_verification_code": None, "email_verification_expires_at": None}},
    )
    logger.info("auth-service: email verificat pentru user_id=%s", user_id)


async def backfill_verification_flags() -> None:
    """Userii creați ÎNAINTE de acest feature nu pot fi puși retroactiv să
    treacă prin verificare cu buletin — le considerăm deja verificați
    (grandfathering). Doar userii înregistrați DE ACUM ÎNAINTE trec prin
    fluxul de onboarding complet. Idempotent, rulat o dată la boot — vezi
    accounts-service::backfill_missing_account_types pentru același pattern."""
    db = get_database()
    result = await db.users.update_many(
        {"email_verified": {"$exists": False}},
        {"$set": {"email_verified": True, "identity_verified": True, "email_verification_code": None, "email_verification_expires_at": None}},
    )
    if result.modified_count:
        logger.info("auth-service: %d useri existenți marcați ca deja verificați (grandfathering)", result.modified_count)


async def mark_identity_verified(user_id: str) -> None:
    """Apelat DOAR de verification-service, după un match facial reușit
    (buletin vs. selfie) — vezi routers/internal.py."""
    db = get_database()
    try:
        object_id = ObjectId(user_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID de utilizator invalid.") from exc

    result = await db.users.update_one({"_id": object_id}, {"$set": {"identity_verified": True}})
    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilizatorul nu există.")
    logger.info("auth-service: identitate verificată pentru user_id=%s", user_id)


async def authenticate_user(payload: UserLogin, *, ip_address: str | None = None, user_agent: str | None = None) -> str:
    db = get_database()
    user = await db.users.find_one({"email": payload.email})

    if user is None or not verify_password(payload.password, user["password_hash"]):
        logger.info("auth-service: autentificare eșuată pentru %s", payload.email)
        await record_login_attempt(
            user_id=str(user["_id"]) if user else None,
            email_attempted=payload.email,
            success=False,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email sau parolă incorectă.")

    if not user.get("is_active", True):
        await record_login_attempt(
            user_id=str(user["_id"]), email_attempted=payload.email, success=False,
            ip_address=ip_address, user_agent=user_agent,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Contul este dezactivat.")

    token = create_access_token(user_id=str(user["_id"]), email=user["email"], role=user.get("role", "customer"))
    await record_login_attempt(
        user_id=str(user["_id"]), email_attempted=payload.email, success=True,
        ip_address=ip_address, user_agent=user_agent,
    )
    logger.info("auth-service: autentificare reușită (user_id=%s)", user["_id"])
    return token


async def get_current_user(authorization: str | None) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Lipsește header-ul Authorization: Bearer <token>.",
        )

    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_access_token(token)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalid sau expirat.") from exc

    try:
        user_object_id = ObjectId(payload.get("sub", ""))
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalid.") from exc

    db = get_database()
    user = await db.users.find_one({"_id": user_object_id})
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilizatorul nu mai există.")

    return user


async def change_password(authorization: str | None, payload: ChangePasswordRequest) -> None:
    """Verifică parola curentă, apoi o înlocuiește cu hash-ul noii parole.

    Reutilizează `get_current_user` (aceeași validare JWT ca /auth/me) —
    identitatea vine STRICT din token, nu dintr-un user_id trimis de UI.
    NU logăm niciodată parola în clar (nici cea curentă, nici cea nouă).
    """
    user = await get_current_user(authorization)

    if not verify_password(payload.current_password, user["password_hash"]):
        logger.info("auth-service: schimbare parolă eșuată (parolă curentă incorectă) pentru user_id=%s", user["_id"])
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Parola curentă este incorectă.")

    db = get_database()
    now = datetime.now(timezone.utc)
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"password_hash": hash_password(payload.new_password), "password_changed_at": now}},
    )
    logger.info("auth-service: parolă schimbată cu succes pentru user_id=%s", user["_id"])


async def verify_user_password(user_id: str, password: str) -> bool:
    """Rută INTERNĂ (service-to-service): confirmă parola userului curent,
    folosit de accounts-service înainte de a dezvălui PAN/CVV la un card
    (acțiune sensibilă — vezi accounts-service app/service.py::reveal_card).
    Nu ridică excepție dacă userul nu există/parola e greșită — întoarce
    doar `False`, ca accounts-service să decidă mesajul afișat userului.
    """
    try:
        object_id = ObjectId(user_id)
    except InvalidId:
        return False

    db = get_database()
    user = await db.users.find_one({"_id": object_id})
    if user is None:
        return False

    return verify_password(password, user["password_hash"])


async def get_user_name(user_id: str) -> dict:
    """Rută INTERNĂ (service-to-service): rezolvă doar numele unui user,
    după user_id — folosit de transactions-service ca să afișeze numele
    contrapărții la un transfer, nu doar IBAN-ul. NU expune email/hash.
    """
    try:
        object_id = ObjectId(user_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID de utilizator invalid.") from exc

    db = get_database()
    user = await db.users.find_one({"_id": object_id})
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilizatorul nu există.")

    return {"first_name": user["first_name"], "last_name": user["last_name"]}


async def get_user_contact(user_id: str) -> dict:
    """Rută INTERNĂ, DOAR pentru personal (transactions-service::routers/staff.py
    — lista de hold-uri de revizuit, unde personalul are nevoie să sune
    clientul). Separată deliberat de get_user_name — restul apelanților nu
    ar trebui să primească email/telefon."""
    try:
        object_id = ObjectId(user_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID de utilizator invalid.") from exc

    db = get_database()
    user = await db.users.find_one({"_id": object_id})
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilizatorul nu există.")

    return {
        "first_name": user["first_name"],
        "last_name": user["last_name"],
        "email": user["email"],
        "phone_number": user.get("phone_number"),
    }


async def get_security_facts(user_id: str) -> dict:
    """Rută INTERNĂ, DOAR pentru transactions-service (motorul de fraudă —
    VEL-04, DEV-01/02/04/05/06). UN SINGUR apel adună tot ce au nevoie
    aceste reguli (istoric login + schimbare parolă + evenimente
    credențiale), ca să nu multiplicăm hop-uri HTTP pe calea de evaluare
    fraud — vezi planul fazei. Toate comparațiile relative la momentul
    tranzacției rămân responsabilitatea APELANTULUI: acest modul întoarce
    STRICT fapte brute, la fel ca get_latest_credential_created_at (DEV-03)."""
    try:
        object_id = ObjectId(user_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID de utilizator invalid.") from exc

    db = get_database()
    user = await db.users.find_one({"_id": object_id})
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilizatorul nu există.")

    # naiv-UTC, nu aware — get_recent_credential_events face comparații
    # Python directe pe datetime-uri citite din Mongo, care vin mereu
    # naive (Motor fără tz_aware=True), indiferent cum au fost scrise.
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=90)
    recent_logins = await get_recent_login_events(user_id)
    recent_credential_events = await webauthn_service.get_recent_credential_events(user_id, since)

    return {
        "recent_logins": recent_logins,
        "password_changed_at": user.get("password_changed_at"),
        "recent_credential_events": recent_credential_events,
    }
