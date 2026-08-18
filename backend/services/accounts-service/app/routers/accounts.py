"""Rute protejate (JWT) ale accounts-service, pentru core banking.

Doar validare (Pydantic/JWT via `CurrentUserId`) și delegare către
app/service.py — logica de business trăiește acolo.

Extern (prin Gateway) acestea devin:
  GET  /api/accounts/me
  GET  /api/accounts/me/cards
  GET  /api/accounts/{account_id}
  POST /api/accounts/dev/fund
"""

from fastapi import APIRouter

from app import service
from app.models import AccountPublicOut, CardOut, DevFundRequest
from app.security import CurrentUserId

router = APIRouter(tags=["accounts"])


@router.get("/me", response_model=AccountPublicOut)
async def get_my_account(user_id: str = CurrentUserId):
    account = await service.get_account_for_user(user_id)
    return service.to_public_account(account)


@router.get("/me/cards", response_model=list[CardOut], response_model_by_alias=False)
async def get_my_cards(user_id: str = CurrentUserId):
    return await service.get_cards_for_user(user_id)


@router.post("/dev/fund", response_model=AccountPublicOut)
async def dev_fund_account(payload: DevFundRequest, user_id: str = CurrentUserId):
    return await service.add_demo_funds(user_id, payload.amount_minor)


@router.get("/{account_id}", response_model=AccountPublicOut)
async def get_account_by_id(account_id: str, user_id: str = CurrentUserId):
    return await service.get_account_by_id_for_user(account_id, user_id)
