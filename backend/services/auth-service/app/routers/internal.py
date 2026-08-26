"""Rute INTERNE ale auth-service — DOAR service-to-service.

Apelabile de alte microservicii (ex. transactions-service, ca să afișeze
numele contrapărții la un transfer), folosind adresa internă Docker
(`http://auth-service:8000`). NU sunt expuse prin API Gateway — gateway
blochează explicit orice path care începe cu "internal/" (vezi
backend/gateway/app/routers/proxy.py), deci nu sunt accesibile din
browser/Angular.
"""

from fastapi import APIRouter, status

from app import service, webauthn_service
from app.models import (
    InternalMarkIdentityVerifiedRequest,
    InternalPasswordVerifyRequest,
    InternalPasswordVerifyResponse,
    InternalSecurityFactsView,
    InternalUserContactView,
    InternalUserNameView,
)
from app.models_webauthn import (
    InternalLatestCredentialView,
    InternalWebauthnVerifyRequest,
    InternalWebauthnVerifyResponse,
)

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/users/{user_id}", response_model=InternalUserNameView)
async def get_user_name(user_id: str):
    return await service.get_user_name(user_id)


@router.get("/users/{user_id}/contact", response_model=InternalUserContactView)
async def get_user_contact(user_id: str):
    return await service.get_user_contact(user_id)


@router.get("/webauthn/credentials/by-user/{user_id}/latest", response_model=InternalLatestCredentialView)
async def get_latest_credential(user_id: str):
    latest_created_at = await webauthn_service.get_latest_credential_created_at(user_id)
    return InternalLatestCredentialView(latest_created_at=latest_created_at)


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


@router.post("/auth/mark-identity-verified", status_code=status.HTTP_204_NO_CONTENT)
async def mark_identity_verified(payload: InternalMarkIdentityVerifiedRequest):
    await service.mark_identity_verified(payload.user_id)


@router.get("/security-facts/{user_id}", response_model=InternalSecurityFactsView)
async def get_security_facts(user_id: str):
    return await service.get_security_facts(user_id)
