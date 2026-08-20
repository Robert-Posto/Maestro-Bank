"""Rute WebAuthn / passkeys ale auth-service.

Doar validare (Pydantic/JWT) și delegare către app/webauthn_service.py —
logica de business trăiește acolo, la fel ca restul serviciului. Identitatea
userului vine STRICT din JWT (header Authorization), niciodată dintr-un
user_id trimis de frontend — la fel ca /auth/me și /auth/change-password.

Extern (prin Gateway) acestea devin:
  POST   /api/auth/webauthn/register/options   (JWT)
  POST   /api/auth/webauthn/register/verify    (JWT)
  POST   /api/auth/webauthn/login/options      (public — nu știm încă cine e userul)
  POST   /api/auth/webauthn/login/verify       (public)
  GET    /api/auth/webauthn/credentials        (JWT)
  DELETE /api/auth/webauthn/credentials/{id}   (JWT)
  POST   /api/auth/webauthn/stepup/options     (JWT)
"""

from fastapi import APIRouter, Header, status

from app import webauthn_service
from app.models import TokenResponse
from app.models_webauthn import (
    CredentialOut,
    WebauthnLoginOptionsRequest,
    WebauthnLoginVerifyRequest,
    WebauthnOptionsOut,
    WebauthnRegisterVerifyRequest,
    WebauthnStepUpOptionsRequest,
)
from app.service import get_current_user

router = APIRouter(prefix="/auth/webauthn", tags=["webauthn"])


@router.post("/register/options", response_model=WebauthnOptionsOut)
async def register_options(authorization: str | None = Header(default=None)):
    user = await get_current_user(authorization)
    challenge_id, options = await webauthn_service.begin_registration(user)
    return WebauthnOptionsOut(challenge_id=challenge_id, options=options)


@router.post(
    "/register/verify",
    response_model=CredentialOut,
    response_model_by_alias=False,
    status_code=status.HTTP_201_CREATED,
)
async def register_verify(payload: WebauthnRegisterVerifyRequest, authorization: str | None = Header(default=None)):
    user = await get_current_user(authorization)
    return await webauthn_service.finish_registration(user, payload.challenge_id, payload.credential)


@router.post("/login/options", response_model=WebauthnOptionsOut)
async def login_options(payload: WebauthnLoginOptionsRequest):
    challenge_id, options = await webauthn_service.begin_login(payload.email)
    return WebauthnOptionsOut(challenge_id=challenge_id, options=options)


@router.post("/login/verify", response_model=TokenResponse)
async def login_verify(payload: WebauthnLoginVerifyRequest):
    token, _user = await webauthn_service.finish_login(payload.challenge_id, payload.credential)
    return TokenResponse(access_token=token)


@router.get("/credentials", response_model=list[CredentialOut], response_model_by_alias=False)
async def list_credentials(authorization: str | None = Header(default=None)):
    user = await get_current_user(authorization)
    return await webauthn_service.list_credentials(str(user["_id"]))


@router.delete("/credentials/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_credential(credential_id: str, authorization: str | None = Header(default=None)):
    user = await get_current_user(authorization)
    await webauthn_service.revoke_credential(str(user["_id"]), credential_id)


@router.post("/stepup/options", response_model=WebauthnOptionsOut)
async def stepup_options(payload: WebauthnStepUpOptionsRequest, authorization: str | None = Header(default=None)):
    user = await get_current_user(authorization)
    challenge_id, options = await webauthn_service.begin_step_up(str(user["_id"]), payload.action, payload.action_payload)
    return WebauthnOptionsOut(challenge_id=challenge_id, options=options)
