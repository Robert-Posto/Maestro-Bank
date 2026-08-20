"""Validare JWT în ai-orchestrator-service — independent de Gateway (defense
in depth, exact ca în celelalte microservicii — vezi accounts-service/app/security.py).
Necesită JWT_SECRET / JWT_ALGORITHM identice cu auth-service și gateway.

Identitatea userului vine STRICT din JWT — vezi task-ul Spending + Forecast
Agent, secțiunea 8: "Agentul NU primește și NU acceptă arbitrar user_id din
prompt." Nu există niciun parametru user_id în request body/query.
"""

from dataclasses import dataclass

import jwt
from fastapi import Depends, Header, HTTPException, status

from app.config import settings


def _decode(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalid sau expirat.") from exc


@dataclass(frozen=True)
class AuthContext:
    """Identitatea userului curent + header-ul Authorization brut, gata de
    propagat neschimbat către Gateway în fiecare apel de tool (vezi
    app/tools/*) — Gateway-ul își face oricum propria validare JWT
    independentă (defense in depth), deci nu reconstruim un token nou aici.
    """

    user_id: str
    authorization_header: str


async def get_auth_context(authorization: str | None = Header(default=None)) -> AuthContext:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Lipsește header-ul Authorization: Bearer <token>.",
        )
    token = authorization.split(" ", 1)[1]
    payload = _decode(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalid: lipsește subiectul.")
    return AuthContext(user_id=user_id, authorization_header=authorization)


CurrentAuth = Depends(get_auth_context)
