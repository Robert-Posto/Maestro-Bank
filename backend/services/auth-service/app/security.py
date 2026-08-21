"""Hashing de parole (bcrypt) și emitere/validare JWT pentru auth-service.

Parolele nu sunt niciodată salvate sau logate în clar — doar hash-ul bcrypt
ajunge în MongoDB, în câmpul `password_hash`.
"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(user_id: str, email: str, role: str = "customer") -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expires_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Aruncă jwt.PyJWTError dacă tokenul e invalid sau expirat."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
