"""Validare JWT în accounts-service — independent de Gateway (defense in
depth). Necesită JWT_SECRET / JWT_ALGORITHM identice cu auth-service și
gateway (setate din docker-compose.yml).
"""

import jwt
from fastapi import Depends, Header, HTTPException, status

from app.config import settings


def _decode(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalid sau expirat.") from exc


def _extract_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Lipsește header-ul Authorization: Bearer <token>.",
        )
    return authorization.split(" ", 1)[1]


async def get_current_user_id(authorization: str | None = Header(default=None)) -> str:
    payload = _decode(_extract_token(authorization))
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalid: lipsește subiectul.")
    return user_id


async def require_staff(authorization: str | None = Header(default=None)) -> str:
    """Ca get_current_user_id, dar cere ȘI claim-ul "role"="staff" din JWT
    (adăugat de auth-service::create_access_token). Gateway-ul cere DEJA un
    JWT valid pentru orice rută a acestui serviciu — asta e stratul FIN,
    "e chiar rolul potrivit", verificat aici, nu la Gateway. Vezi
    transactions-service/app/security.py::require_staff — pattern identic,
    reprodus aici, nu importat (fiecare serviciu își validează independent
    JWT-ul, defense in depth, la fel ca restul acestui fișier)."""
    payload = _decode(_extract_token(authorization))
    if payload.get("role") != "staff":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acces permis doar personalului.")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalid: lipsește subiectul.")
    return user_id


CurrentUserId = Depends(get_current_user_id)
RequireStaff = Depends(require_staff)
