"""Validare JWT la nivel de Gateway.

Folosește același JWT_SECRET / JWT_ALGORITHM ca auth-service (setate
identic în docker-compose.yml), astfel încât un token emis de
auth-service să fie verificabil direct aici, fără a mai apela
auth-service doar pentru validare.
"""

import jwt
from fastapi import Header, HTTPException, status

from app.config import settings


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalid sau expirat.") from exc


async def get_current_user_id(authorization: str | None = Header(default=None)) -> str:
    """Dependency FastAPI: extrage și validează Bearer token-ul din header.

    De folosit cu `Depends(get_current_user_id)` pe orice rută de Gateway
    care trebuie protejată (ex. /api/auth/me). Rutele publice (register,
    login, health) nu folosesc această dependency.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Lipsește header-ul Authorization: Bearer <token>.",
        )

    token = authorization.split(" ", 1)[1]
    payload = decode_token(token)

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalid: lipsește subiectul.")

    return user_id
