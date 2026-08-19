"""Logica de business a auth-service.

Separată de routing (`app/routers/auth.py`, care doar validează input-ul
și deleagă aici) și de modele (`app/models.py`, care doar definește
DTO-urile). Acest modul e singurul care atinge `db.users` direct și
singurul care cheamă alte servicii (accounts-service, la provisioning).
"""

import logging
from datetime import datetime, timezone

import httpx
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status

from app.config import settings
from app.database import get_database
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


async def register_user(payload: UserRegister) -> dict:
    db = get_database()

    existing = await db.users.find_one({"email": payload.email})
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Există deja un cont cu acest email.")

    user_doc = {
        "first_name": payload.first_name,
        "last_name": payload.last_name,
        "email": payload.email,
        # Doar hash-ul ajunge în baza de date — parola în clar nu e
        # niciodată salvată sau logată.
        "password_hash": hash_password(payload.password),
        "created_at": datetime.now(timezone.utc),
        "is_active": True,
    }
    result = await db.users.insert_one(user_doc)
    user_id = str(result.inserted_id)
    logger.info("auth-service: cont nou creat (user_id=%s)", user_id)

    await _provision_bank_account(user_id)

    return await db.users.find_one({"_id": result.inserted_id})


async def authenticate_user(payload: UserLogin) -> str:
    db = get_database()
    user = await db.users.find_one({"email": payload.email})

    if user is None or not verify_password(payload.password, user["password_hash"]):
        logger.info("auth-service: autentificare eșuată pentru %s", payload.email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email sau parolă incorectă.")

    if not user.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Contul este dezactivat.")

    token = create_access_token(user_id=str(user["_id"]), email=user["email"])
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
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"password_hash": hash_password(payload.new_password)}},
    )
    logger.info("auth-service: parolă schimbată cu succes pentru user_id=%s", user["_id"])


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
