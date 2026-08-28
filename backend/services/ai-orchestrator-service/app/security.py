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
from app.i18n import translate


def _decode(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=translate("tokenInvalidOrExpired")
        ) from exc


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
            detail=translate("missingAuthorizationHeader"),
        )
    token = authorization.split(" ", 1)[1]
    payload = _decode(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=translate("tokenMissingSubject"))
    return AuthContext(user_id=user_id, authorization_header=authorization)


CurrentAuth = Depends(get_auth_context)


# --- Support Agent (vezi app/agents/support.py) --------------------------
# Support Agent nu ia nicio decizie de autorizare pe baza user_id-ului
# extras dintr-un token — doar retransmite header-ul BRUT ("Bearer <token>")
# neschimbat către Gateway la fiecare tool call (vezi app/tools/support_*).
# Gateway-ul + fiecare microserviciu din spate fac toată izolarea per-user,
# exact ca pentru orice alt client (Angular inclusiv). De-aia dependency-ul
# de mai jos întoarce direct header-ul, nu un AuthContext structurat.
async def get_authorization(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=translate("missingAuthorizationHeader"),
        )
    token = authorization.split(" ", 1)[1]
    _decode(token)  # doar validare — ridică 401 dacă tokenul e invalid/expirat
    return authorization


CurrentAuthorization = Depends(get_authorization)


# --- Persistență de conversații (vezi app/services/conversation_service.py) -
# user_id folosit STRICT ca cheie de proprietate a unei conversații stocate
# — NU e trecut agentului/tool-urilor (acelea rămân pe get_authorization de
# mai sus, neschimbat) — deci nu încalcă principiul de mai sus.
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
