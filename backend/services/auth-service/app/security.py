"""Hashing de parole (bcrypt) și emitere/validare JWT pentru auth-service.

Parolele nu sunt niciodată salvate sau logate în clar — doar hash-ul bcrypt
ajunge în MongoDB, în câmpul `password_hash`.
"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Header, HTTPException, status

from app.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(user_id: str, email: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expires_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Aruncă jwt.PyJWTError dacă tokenul e invalid sau expirat."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def get_current_user_id_from_header(authorization: str | None = Header(default=None)) -> str:
    """Ca accounts-service::get_current_user_id — doar extrage user_id din
    JWT, fără căutare în bază (folosit de rutele care nu au nevoie de tot
    documentul userului, ex. verify-email)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Lipsește header-ul Authorization: Bearer <token>.",
        )
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalid sau expirat.") from exc

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalid: lipsește subiectul.")
    return user_id
