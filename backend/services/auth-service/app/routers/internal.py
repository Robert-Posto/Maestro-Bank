"""Rute INTERNE ale auth-service — DOAR service-to-service.

Apelabile de alte microservicii (ex. transactions-service, ca să afișeze
numele contrapărții la un transfer), folosind adresa internă Docker
(`http://auth-service:8000`). NU sunt expuse prin API Gateway — gateway
blochează explicit orice path care începe cu "internal/" (vezi
backend/gateway/app/routers/proxy.py), deci nu sunt accesibile din
browser/Angular.
"""

from fastapi import APIRouter

from app import service, webauthn_service
from app.models import InternalPasswordVerifyRequest, InternalPasswordVerifyResponse, InternalUserNameView
from app.models_webauthn import InternalWebauthnVerifyRequest, InternalWebauthnVerifyResponse

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/users/{user_id}", response_model=InternalUserNameView)
async def get_user_name(user_id: str):
    return await service.get_user_name(user_id)


@router.post("/auth/verify-password", response_model=InternalPasswordVerifyResponse)
async def verify_password(payload: InternalPasswordVerifyRequest):
    valid = await service.verify_user_password(payload.user_id, payload.password)
    return InternalPasswordVerifyResponse(valid=valid)


@router.post("/auth/verify-webauthn", response_model=InternalWebauthnVerifyResponse)
async def verify_webauthn(payload: InternalWebauthnVerifyRequest):
    valid = await webauthn_service.verify_step_up(
        payload.user_id, payload.challenge_id, payload.action, payload.action_payload, payload.credential
    )
    return InternalWebauthnVerifyResponse(valid=valid)
