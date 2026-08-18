"""Rutele de autentificare ale auth-service.

Extern (prin Gateway) acestea devin: /api/auth/register, /api/auth/login,
/api/auth/me — vezi backend/gateway/app/routers/proxy.py.
"""

import logging
from datetime import datetime, timezone

import httpx
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Header, HTTPException, status

from app.config import settings
from app.database import get_database
from app.models import TokenResponse, UserLogin, UserMeOut, UserOut, UserRegister
from app.security import create_access_token, decode_access_token, hash_password, verify_password

logger = logging.getLogger("auth-service")

router = APIRouter(prefix="/auth", tags=["auth"])


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


@router.post(
    "/register",
    response_model=UserOut,
    response_model_by_alias=False,
    status_code=status.HTTP_201_CREATED,
)
async def register(payload: UserRegister):
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

    created = await db.users.find_one({"_id": result.inserted_id})
    return created


@router.post("/login", response_model=TokenResponse)
async def login(payload: UserLogin):
    db = get_database()
    user = await db.users.find_one({"email": payload.email})

    if user is None or not verify_password(payload.password, user["password_hash"]):
        logger.info("auth-service: autentificare eșuată pentru %s", payload.email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email sau parolă incorectă.")

    if not user.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Contul este dezactivat.")

    token = create_access_token(user_id=str(user["_id"]), email=user["email"])
    logger.info("auth-service: autentificare reușită (user_id=%s)", user["_id"])
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserMeOut, response_model_by_alias=False)
async def get_me(authorization: str | None = Header(default=None)):
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
