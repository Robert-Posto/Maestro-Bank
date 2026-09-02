"""Validare JWT în loans-service — independent de Gateway (defense in
depth). Necesită JWT_SECRET / JWT_ALGORITHM identice cu celelalte servicii
(setate din docker-compose.yml).
"""

import jwt
from fastapi import Depends, Header, HTTPException, status

from app.config import settings
from app.i18n import translate


def _decode(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=translate("tokenInvalidOrExpired")
        ) from exc


async def get_current_user_id(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=translate("missingAuthorizationHeader"),
        )
    token = authorization.split(" ", 1)[1]
    payload = _decode(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=translate("tokenMissingSubject"))
    return user_id


CurrentUserId = Depends(get_current_user_id)


async def require_staff(authorization: str | None = Header(default=None)) -> str:
    """Ca get_current_user_id, dar cere ȘI claim-ul "role"="staff" din JWT —
    identic ca tipar cu transactions-service/app/security.py::require_staff.
    Apărare suplimentară (defense in depth) — Gateway-ul oricum forwardează
    orice JWT valid către /api/loans/*, verificarea de rol e făcută AICI,
    de acest serviciu, nu doar la nivel de proxy."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=translate("missingAuthorizationHeader"),
        )
    token = authorization.split(" ", 1)[1]
    payload = _decode(token)
    if payload.get("role") != "staff":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=translate("staffOnly"))
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=translate("tokenMissingSubject"))
    return user_id


RequireStaff = Depends(require_staff)
