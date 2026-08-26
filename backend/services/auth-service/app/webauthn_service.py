"""Logica WebAuthn (passkeys) pentru auth-service.

Separată de service.py (users/parole) — suprafață mare, conceptual
distinctă. Colecțiile `webauthn_credentials` și `webauthn_challenges`
trăiesc tot în auth_db (alături de `users`), pentru că verificarea
credențialelor e responsabilitatea auth-service, la fel ca verificarea
parolei (vezi service.py::verify_user_password, folosit de
accounts-service prin /internal/auth/verify-password). accounts-service
rămâne un simplu consumator, prin noul /internal/auth/verify-webauthn —
vezi routers/internal.py.

NU stocăm NICIODATĂ date biometrice — doar un credential_id opac, o cheie
publică (COSE) și un contor de semnătură. Verificarea propriu-zisă
(semnătură, origin, rp_id, user-verification) e făcută integral de
pachetul `webauthn` (py_webauthn) — acest modul NU reimplementează nimic
din criptografia WebAuthn, doar orchestrează challenge-uri + stocare.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError
from webauthn import (
    base64url_to_bytes,
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import options_to_json_dict
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, InvalidRegistrationResponse
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.config import settings
from app.database import get_database
from app.login_events import record_login_attempt
from app.security import create_access_token

logger = logging.getLogger("auth-service")

_MAX_CREDENTIALS_PER_USER = 8  # cap defensiv demo — evită înregistrare nelimitată
_GENERIC_NO_PASSKEY_DETAIL = "Nu există niciun passkey înregistrat pentru acest email."
# Revocarea e soft-delete (`revoked_at`, vezi revoke_credential) — DEV-02
# (fraud) are nevoie să "vadă" o revocare recentă. Orice altă interogare
# din acest fișier vrea DOAR credențiale ACTIVE — filtrul de mai jos,
# refolosit peste tot, ca un site de citire să nu uite să-l adauge.
_ACTIVE_CREDENTIAL_FILTER = {"revoked_at": None}


# --- setup (apelat din lifespan — NU există migrări, indexarea e idempotentă,
#     la fel ca accounts-service::backfill_missing_account_types) -----------


async def ensure_webauthn_indexes() -> None:
    db = get_database()
    await db.webauthn_credentials.create_index("credential_id", unique=True)
    await db.webauthn_credentials.create_index("user_id")
    # TTL nativ Mongo — dar NU e singura linie de apărare, vezi
    # _consume_challenge: thread-ul de TTL rulează la interval de ~60s,
    # insuficient pentru "single-use strict" (o cerere chiar înainte de
    # sweep tot ar trebui respinsă dacă a expirat deja logic).
    await db.webauthn_challenges.create_index("expires_at", expireAfterSeconds=0)


# --- helpers interne ---------------------------------------------------


def _new_challenge_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=settings.webauthn_challenge_ttl_seconds)


async def _store_challenge(
    *,
    user_id: str | None,
    purpose: str,
    challenge: bytes,
    action: str | None = None,
    action_payload: str | None = None,
) -> str:
    db = get_database()
    doc = {
        "user_id": user_id,
        "purpose": purpose,
        "challenge": challenge,
        "action": action,
        "action_payload": action_payload,
        "created_at": datetime.now(timezone.utc),
        "expires_at": _new_challenge_expiry(),
    }
    result = await db.webauthn_challenges.insert_one(doc)
    return str(result.inserted_id)


async def _consume_challenge(challenge_id: str, purpose: str) -> dict:
    """Găsește + ȘTERGE atomic un challenge — single-use garantat prin
    `find_one_and_delete` (nu ne bazăm pe thread-ul de TTL al Mongo).
    Challenge inexistent, deja folosit SAU expirat -> aceeași eroare, ca
    să nu distingem cazurile pentru un eventual atacator."""
    db = get_database()
    try:
        object_id = ObjectId(challenge_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Challenge invalid.") from exc

    doc = await db.webauthn_challenges.find_one_and_delete({"_id": object_id, "purpose": purpose})
    if doc is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Challenge invalid sau deja folosit.")

    expires_at = doc["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) >= expires_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Challenge expirat.")

    return doc


async def _get_user_by_id(user_id: str) -> dict | None:
    db = get_database()
    try:
        object_id = ObjectId(user_id)
    except InvalidId:
        return None
    return await db.users.find_one({"_id": object_id})


async def _reject_if_sign_count_regressed(stored_credential: dict, credential: dict[str, Any]) -> None:
    """Detectare de clonare: contorul de semnătură ar trebui să crească
    strict la fiecare folosire reală a authenticatorului fizic. `webauthn`
    (verify_authentication_response) respinge el însuși un contor regresat
    — dar doar cu o eroare de validare, fără să revoce nimic. Facem
    verificarea și AICI, separat, ÎNAINTE de verify_authentication_response,
    ca la un contor regresat să putem revoca imediat credențiala compromisă
    (nu doar respinge cererea curentă) — un assertion capturat/clonat nu ar
    mai trebui să funcționeze NICIODATĂ după asta, nu doar de data asta.

    Citim DOAR contorul brut din authenticatorData (offset 33:37 — format:
    rpIdHash[32] + flags[1] + signCount[4], vezi spec WebAuthn §6.1) — NU
    verificăm nimic criptografic aici; semnătura/originea/rp_id/etc. rămân
    integral responsabilitatea verify_authentication_response, apelat DUPĂ
    această verificare. Contor 0 pe ambele părți e normal la mulți
    authenticatori (inclusiv cei Apple) — NU respingem acest caz.
    """
    auth_data_b64 = credential.get("response", {}).get("authenticatorData")
    if not isinstance(auth_data_b64, str):
        return  # payload malformat — las verify_authentication_response să-l respingă cu un mesaj clar

    auth_data = base64url_to_bytes(auth_data_b64)
    if len(auth_data) < 37:
        return

    new_sign_count = int.from_bytes(auth_data[33:37], "big")
    stored_count = stored_credential["sign_count"]

    if stored_count != 0 and new_sign_count <= stored_count:
        db = get_database()
        # Soft-delete, ca la revoke_credential — și o revocare AUTOMATĂ
        # (clonare suspectată) e exact tipul de eveniment pe care DEV-02
        # (fraud) trebuie să-l vadă.
        await db.webauthn_credentials.update_one(
            {"_id": stored_credential["_id"]}, {"$set": {"revoked_at": datetime.now(timezone.utc)}}
        )
        logger.error(
            "auth-service: contor de semnătură regresat pentru credential_id=%s (user_id=%s) — posibilă "
            "clonare, credențiala a fost revocată automat.",
            stored_credential["credential_id"],
            stored_credential["user_id"],
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Acest passkey pare compromis și a fost revocat automat. Adaugă unul nou.",
        )


async def _record_successful_use(stored_credential: dict, new_sign_count: int) -> None:
    db = get_database()
    await db.webauthn_credentials.update_one(
        {"_id": stored_credential["_id"]},
        {"$set": {"sign_count": new_sign_count, "last_used_at": datetime.now(timezone.utc)}},
    )


async def _find_stored_credential(credential: dict[str, Any], *, user_id: str | None = None) -> dict | None:
    raw_id = credential.get("rawId") or credential.get("id")
    if not isinstance(raw_id, str):
        return None

    db = get_database()
    query: dict[str, Any] = {"credential_id": base64url_to_bytes(raw_id), **_ACTIVE_CREDENTIAL_FILTER}
    if user_id is not None:
        query["user_id"] = user_id
    return await db.webauthn_credentials.find_one(query)


# --- înregistrare (enroll un passkey nou) -------------------------------


async def begin_registration(user: dict) -> tuple[str, dict[str, Any]]:
    db = get_database()
    user_id = str(user["_id"])

    existing_count = await db.webauthn_credentials.count_documents({"user_id": user_id, **_ACTIVE_CREDENTIAL_FILTER})
    if existing_count >= _MAX_CREDENTIALS_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ai atins numărul maxim de passkey-uri ({_MAX_CREDENTIALS_PER_USER}).",
        )

    existing = await db.webauthn_credentials.find(
        {"user_id": user_id, **_ACTIVE_CREDENTIAL_FILTER}
    ).to_list(length=_MAX_CREDENTIALS_PER_USER)

    options = generate_registration_options(
        rp_id=settings.webauthn_rp_id,
        rp_name=settings.webauthn_rp_name,
        user_id=ObjectId(user_id).binary,
        user_name=user["email"],
        user_display_name=f"{user['first_name']} {user['last_name']}",
        attestation=AttestationConveyancePreference.NONE,
        authenticator_selection=AuthenticatorSelectionCriteria(
            user_verification=UserVerificationRequirement.REQUIRED,
            resident_key=ResidentKeyRequirement.DISCOURAGED,
        ),
        exclude_credentials=[PublicKeyCredentialDescriptor(id=cred["credential_id"]) for cred in existing],
    )

    challenge_id = await _store_challenge(user_id=user_id, purpose="registration", challenge=options.challenge)
    return challenge_id, options_to_json_dict(options)


async def finish_registration(user: dict, challenge_id: str, credential: dict[str, Any]) -> dict:
    user_id = str(user["_id"])
    challenge_doc = await _consume_challenge(challenge_id, purpose="registration")
    if challenge_doc["user_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Challenge invalid.")

    try:
        verification = verify_registration_response(
            credential=credential,
            expected_challenge=challenge_doc["challenge"],
            expected_rp_id=settings.webauthn_rp_id,
            expected_origin=settings.webauthn_origins,
            require_user_verification=True,
        )
    except InvalidRegistrationResponse as exc:
        logger.info("auth-service: înregistrare passkey eșuată (user_id=%s): %s", user_id, exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nu am putut înregistra passkey-ul.") from exc

    db = get_database()
    now = datetime.now(timezone.utc)
    doc = {
        "user_id": user_id,
        "credential_id": verification.credential_id,
        "public_key": verification.credential_public_key,
        "sign_count": verification.sign_count,
        "created_at": now,
        "last_used_at": None,
        "revoked_at": None,
    }
    try:
        result = await db.webauthn_credentials.insert_one(doc)
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Acest passkey este deja înregistrat.") from exc

    logger.info("auth-service: passkey înregistrat (user_id=%s, credential_id=%s)", user_id, result.inserted_id)
    return await db.webauthn_credentials.find_one({"_id": result.inserted_id})


# --- login (autentificare cu passkey, în loc de parolă) ------------------


async def begin_login(email: str) -> tuple[str, dict[str, Any]]:
    """NU dezvăluie dacă emailul există sau are passkey-uri — challenge_id
    + options au aceeași formă indiferent de caz (allow_credentials gol
    dacă emailul nu are passkey-uri; finish_login eșuează la fel de
    generic mai târziu, oricare ar fi motivul)."""
    db = get_database()
    user = await db.users.find_one({"email": email.strip().lower()})

    allow_credentials: list[PublicKeyCredentialDescriptor] = []
    user_id: str | None = None
    if user is not None:
        user_id = str(user["_id"])
        creds = await db.webauthn_credentials.find(
            {"user_id": user_id, **_ACTIVE_CREDENTIAL_FILTER}
        ).to_list(length=_MAX_CREDENTIALS_PER_USER)
        allow_credentials = [PublicKeyCredentialDescriptor(id=c["credential_id"]) for c in creds]

    options = generate_authentication_options(
        rp_id=settings.webauthn_rp_id,
        user_verification=UserVerificationRequirement.REQUIRED,
        allow_credentials=allow_credentials or None,
    )
    challenge_id = await _store_challenge(user_id=user_id, purpose="login", challenge=options.challenge)
    return challenge_id, options_to_json_dict(options)


async def finish_login(
    challenge_id: str, credential: dict[str, Any], *, ip_address: str | None = None, user_agent: str | None = None
) -> tuple[str, dict]:
    """Întoarce (access_token, user_doc) — reutilizează STRICT
    create_access_token, aceeași funcție folosită de login cu parolă
    (service.py::authenticate_user), ca sesiunea rezultată să fie identică
    indiferent de metoda de autentificare. Înregistrează un login_events
    DOAR pe succes — spre deosebire de parolă, un eșec aici nu e un semnal
    util de tip "ghicire" (nu poți "ghici" un passkey), deci VEL-04 nu are
    nevoie de eșecurile de-aici."""
    challenge_doc = await _consume_challenge(challenge_id, purpose="login")
    user_id = challenge_doc.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_GENERIC_NO_PASSKEY_DETAIL)

    stored = await _find_stored_credential(credential, user_id=user_id)
    if stored is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_GENERIC_NO_PASSKEY_DETAIL)

    await _reject_if_sign_count_regressed(stored, credential)

    try:
        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge_doc["challenge"],
            expected_rp_id=settings.webauthn_rp_id,
            expected_origin=settings.webauthn_origins,
            credential_public_key=stored["public_key"],
            credential_current_sign_count=stored["sign_count"],
            require_user_verification=True,
        )
    except InvalidAuthenticationResponse as exc:
        logger.info("auth-service: autentificare passkey eșuată (user_id=%s): %s", user_id, exc)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_GENERIC_NO_PASSKEY_DETAIL) from exc

    await _record_successful_use(stored, verification.new_sign_count)

    user = await _get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_GENERIC_NO_PASSKEY_DETAIL)

    token = create_access_token(user_id=str(user["_id"]), email=user["email"], role=user.get("role", "customer"))
    await record_login_attempt(
        user_id=str(user["_id"]), email_attempted=user["email"], success=True,
        ip_address=ip_address, user_agent=user_agent,
    )
    return token, user


# --- step-up (re-confirmare biometrică pentru o acțiune sensibilă) -------
# Folosit azi DOAR de accounts-service, la reveal card (vezi
# /internal/auth/verify-webauthn în routers/internal.py) — dar construit
# generic, ca să poată fi reutilizat de orice altă acțiune sensibilă pe
# viitor, fără schimbări aici.


async def begin_step_up(user_id: str, action: str, action_payload: str) -> tuple[str, dict[str, Any]]:
    db = get_database()
    creds = await db.webauthn_credentials.find(
        {"user_id": user_id, **_ACTIVE_CREDENTIAL_FILTER}
    ).to_list(length=_MAX_CREDENTIALS_PER_USER)
    if not creds:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nu ai niciun passkey înregistrat.")

    options = generate_authentication_options(
        rp_id=settings.webauthn_rp_id,
        user_verification=UserVerificationRequirement.REQUIRED,
        allow_credentials=[PublicKeyCredentialDescriptor(id=c["credential_id"]) for c in creds],
    )
    challenge_id = await _store_challenge(
        user_id=user_id,
        purpose="step-up",
        challenge=options.challenge,
        action=action,
        action_payload=action_payload,
    )
    return challenge_id, options_to_json_dict(options)


async def verify_step_up(user_id: str, challenge_id: str, action: str, action_payload: str, credential: dict[str, Any]) -> bool:
    """Apelat DOAR din routers/internal.py — contract "nu ridică niciodată
    excepție, doar întoarce False", la fel ca verify_user_password, ca
    serviciul apelant (accounts-service) să decidă mesajul afișat userului."""
    try:
        challenge_doc = await _consume_challenge(challenge_id, purpose="step-up")
    except HTTPException:
        return False

    if (
        challenge_doc.get("user_id") != user_id
        or challenge_doc.get("action") != action
        or challenge_doc.get("action_payload") != action_payload
    ):
        return False

    stored = await _find_stored_credential(credential, user_id=user_id)
    if stored is None:
        return False

    try:
        await _reject_if_sign_count_regressed(stored, credential)
    except HTTPException:
        return False

    try:
        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge_doc["challenge"],
            expected_rp_id=settings.webauthn_rp_id,
            expected_origin=settings.webauthn_origins,
            credential_public_key=stored["public_key"],
            credential_current_sign_count=stored["sign_count"],
            require_user_verification=True,
        )
    except InvalidAuthenticationResponse:
        return False

    await _record_successful_use(stored, verification.new_sign_count)
    return True


# --- management (listare/revocare) ---------------------------------------


async def list_credentials(user_id: str) -> list[dict]:
    db = get_database()
    return await db.webauthn_credentials.find(
        {"user_id": user_id, **_ACTIVE_CREDENTIAL_FILTER}
    ).sort("created_at", -1).to_list(length=_MAX_CREDENTIALS_PER_USER)


async def get_latest_credential_created_at(user_id: str) -> datetime | None:
    """Data înrolării celui mai recent passkey ACTIV al userului — folosit
    intern de transactions-service (regula fraud DEV-03). Acoperit deja de
    indexul `user_id` (vezi ensure_webauthn_indexes), fără index nou
    necesar."""
    db = get_database()
    latest = await db.webauthn_credentials.find(
        {"user_id": user_id, **_ACTIVE_CREDENTIAL_FILTER}
    ).sort("created_at", -1).limit(1).to_list(length=1)
    return latest[0]["created_at"] if latest else None


async def get_recent_credential_events(user_id: str, since: datetime) -> list[dict]:
    """Evenimente de ÎNROLARE ȘI REVOCARE din fereastra dată — DOAR pentru
    DEV-02 (fraud): "credențială schimbată recent" înseamnă ambele
    direcții, spre deosebire de get_latest_credential_created_at (DEV-03),
    care vrea STRICT înrolări active. Un credential revocat ȘI re-înrolat
    în aceeași fereastră apare ca DOUĂ evenimente separate, corect."""
    db = get_database()
    docs = await db.webauthn_credentials.find(
        {"user_id": user_id, "$or": [{"created_at": {"$gte": since}}, {"revoked_at": {"$gte": since}}]}
    ).to_list(length=_MAX_CREDENTIALS_PER_USER * 2)  # *2: fiecare doc poate produce până la 2 evenimente

    events: list[dict] = []
    for doc in docs:
        if doc["created_at"] >= since:
            events.append({"event": "enrolled", "created_at": doc["created_at"]})
        if doc.get("revoked_at") and doc["revoked_at"] >= since:
            events.append({"event": "revoked", "created_at": doc["revoked_at"]})
    return events


async def revoke_credential(user_id: str, credential_id: str) -> None:
    """Soft-delete (`revoked_at`), NU `delete_one` — DEV-02 (fraud) are
    nevoie să "vadă" o revocare recentă ca semnal de posibil account
    takeover. Toate CELELALTE interogări din acest fișier filtrează
    explicit `_ACTIVE_CREDENTIAL_FILTER`, deci o credențială revocată
    dispare din orice listă/verificare de autentificare exact ca înainte —
    doar rămâne, invizibilă, pentru acest singur consumator nou."""
    db = get_database()
    try:
        object_id = ObjectId(credential_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID de passkey invalid.") from exc

    result = await db.webauthn_credentials.update_one(
        {"_id": object_id, "user_id": user_id, **_ACTIVE_CREDENTIAL_FILTER},
        {"$set": {"revoked_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Passkey-ul nu există.")
