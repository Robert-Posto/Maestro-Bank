"""Rute protejate (JWT) pentru obiective de economisire ("Pockets").

Doar validare (Pydantic/JWT via `CurrentUserId`) și delegare către
app/service.py — logica de business trăiește acolo.

Extern (prin Gateway) acestea devin:
  GET    /api/accounts/pockets
  POST   /api/accounts/pockets
  POST   /api/accounts/pockets/{pocket_id}/deposit
  POST   /api/accounts/pockets/{pocket_id}/withdraw
  DELETE /api/accounts/pockets/{pocket_id}

NOTĂ: prefixul "/pockets" e un router SEPARAT de accounts_router (care are
GET /{account_id} la rădăcină) tocmai ca să nu existe nicio ambiguitate
de rutare între cele două — vezi același motiv documentat în cards.py.
"""

from fastapi import APIRouter, status

from app import service
from app.models import PocketAmountRequest, PocketCreateRequest, PocketOut
from app.security import CurrentUserId

router = APIRouter(prefix="/pockets", tags=["pockets"])


@router.get("", response_model=list[PocketOut], response_model_by_alias=False)
async def list_pockets(user_id: str = CurrentUserId):
    pockets = await service.get_pockets_for_user(user_id)
    return [service.to_pocket_out(p) for p in pockets]


@router.post("", response_model=PocketOut, response_model_by_alias=False, status_code=status.HTTP_201_CREATED)
async def create_pocket(payload: PocketCreateRequest, user_id: str = CurrentUserId):
    pocket = await service.create_pocket(user_id, payload.name, payload.target_minor)
    return service.to_pocket_out(pocket)


@router.post("/{pocket_id}/deposit", response_model=PocketOut, response_model_by_alias=False)
async def deposit(pocket_id: str, payload: PocketAmountRequest, user_id: str = CurrentUserId):
    pocket = await service.deposit_to_pocket(pocket_id, user_id, payload.amount_minor)
    return service.to_pocket_out(pocket)


@router.post("/{pocket_id}/withdraw", response_model=PocketOut, response_model_by_alias=False)
async def withdraw(pocket_id: str, payload: PocketAmountRequest, user_id: str = CurrentUserId):
    pocket = await service.withdraw_from_pocket(pocket_id, user_id, payload.amount_minor)
    return service.to_pocket_out(pocket)


@router.delete("/{pocket_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pocket(pocket_id: str, user_id: str = CurrentUserId):
    await service.delete_pocket(pocket_id, user_id)
