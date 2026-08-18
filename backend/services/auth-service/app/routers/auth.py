"""Rutele de autentificare ale auth-service.

Doar validare (Pydantic) și delegare către app/service.py — logica de
business (acces la bază, hashing, provisioning) trăiește acolo.

Extern (prin Gateway) acestea devin: /api/auth/register, /api/auth/login,
/api/auth/me — vezi backend/gateway/app/routers/proxy.py.
"""

from fastapi import APIRouter, Header, status

from app import service
from app.models import TokenResponse, UserLogin, UserMeOut, UserOut, UserRegister

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
