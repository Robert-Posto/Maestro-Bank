"""Rutele de autentificare ale auth-service.

Doar validare (Pydantic) și delegare către app/service.py — logica de
business (acces la bază, hashing, provisioning) trăiește acolo.

Extern (prin Gateway) acestea devin: /api/auth/register, /api/auth/login,
/api/auth/me, /api/auth/verify-email, /api/auth/resend-verification-email
— vezi backend/gateway/app/routers/proxy.py.
"""

from fastapi import APIRouter, Depends, Header, status

from app import service
from app.models import ChangePasswordRequest, EmailVerifyRequest, TokenResponse, UserLogin, UserMeOut, UserOut, UserRegister
from app.security import get_current_user_id_from_header

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserOut,
    response_model_by_alias=False,
    status_code=status.HTTP_201_CREATED,
)
async def register(payload: UserRegister):
    return await service.register_user(payload)


@router.post("/login", response_model=TokenResponse)
async def login(payload: UserLogin):
    token = await service.authenticate_user(payload)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserMeOut, response_model_by_alias=False)
async def get_me(authorization: str | None = Header(default=None)):
    return await service.get_current_user(authorization)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(payload: ChangePasswordRequest, authorization: str | None = Header(default=None)):
    await service.change_password(authorization, payload)


@router.post("/verify-email", status_code=status.HTTP_204_NO_CONTENT)
async def verify_email(payload: EmailVerifyRequest, user_id: str = Depends(get_current_user_id_from_header)):
    await service.verify_email_code(user_id, payload.code)


@router.post("/resend-verification-email", status_code=status.HTTP_204_NO_CONTENT)
async def resend_verification_email(user_id: str = Depends(get_current_user_id_from_header)):
    await service.send_verification_code(user_id)
