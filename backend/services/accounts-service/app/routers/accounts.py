"""Rute protejate (JWT) ale accounts-service, pentru core banking.

Doar validare (Pydantic/JWT via `CurrentUserId`) și delegare către
app/service.py — logica de business trăiește acolo.

Extern (prin Gateway) acestea devin:
  GET  /api/accounts/me
  GET  /api/accounts/me/cards
  GET  /api/accounts/all
  POST /api/accounts/new
  GET  /api/accounts/{account_id}
  POST /api/accounts/dev/fund

NOTĂ despre ordine: "/all" și "/new" sunt înregistrate ÎNAINTE de
"/{account_id}" (mai jos în acest fișier) din același motiv ca "/me" —
FastAPI potrivește rutele în ordinea înregistrării, iar "/{account_id}"
ar "înghiți" orice path de un singur segment (inclusiv "all"/"new") dacă
ar fi înregistrat primul.
"""

from fastapi import APIRouter, status

from app import service
from app.models import AccountCreateRequest, AccountPublicOut, CardOut, DevFundRequest
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


@router.get("/all", response_model=list[AccountPublicOut])
async def get_all_accounts(user_id: str = CurrentUserId):
    accounts = await service.list_accounts_for_user(user_id)
    return [service.to_public_account(account) for account in accounts]


@router.post("/new", response_model=AccountPublicOut, status_code=status.HTTP_201_CREATED)
async def open_new_account(payload: AccountCreateRequest, user_id: str = CurrentUserId):
    return await service.create_additional_account(user_id, payload.account_type, payload.document_filename)


@router.get("/{account_id}", response_model=AccountPublicOut)
async def get_account_by_id(account_id: str, user_id: str = CurrentUserId):
    return await service.get_account_by_id_for_user(account_id, user_id)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def close_account(account_id: str, user_id: str = CurrentUserId):
    await service.delete_account(user_id, account_id)
