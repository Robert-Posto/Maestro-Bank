"""Validare JWT în ai-orchestrator-service — independent de Gateway
(defense in depth), pattern IDENTIC cu celelalte microservicii.

Diferență importantă față de celelalte servicii: Support Agent nu are
bază de date proprie și nu ia NICIO decizie de autorizare pe baza
user_id-ului extras dintr-un token — de-aia `get_authorization` întoarce
header-ul BRUT ("Bearer <token>"), gata de retransmis neschimbat către
Gateway la fiecare tool call (vezi app/tools/*). Gateway-ul + fiecare
microserviciu din spate fac toată izolarea per-user, exact ca pentru
orice alt client (Angular inclusiv) — agentul nu duplică acea logică.
"""

import jwt
from fastapi import Depends, Header, HTTPException, status

from app.config import settings


def _decode(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalid sau expirat.") from exc


async def get_authorization(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Lipsește header-ul Authorization: Bearer <token>.",
        )
    token = authorization.split(" ", 1)[1]
    _decode(token)  # doar validare — ridică 401 dacă tokenul e invalid/expirat
    return authorization


CurrentAuthorization = Depends(get_authorization)
