"""Rute protejate (JWT) ale transactions-service.

Doar validare (Pydantic/JWT via `CurrentUserId`) și delegare către
app/service.py — logica de business trăiește acolo.

Extern (prin Gateway) acestea devin:
  POST /api/transactions/transfers
  GET  /api/transactions
  GET  /api/transactions/{id}
"""

from fastapi import APIRouter, Query

from app import service
from app.models import TransactionOut, TransferRequest
from app.security import CurrentUserId

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post("/transfers", response_model=TransactionOut, response_model_by_alias=False, status_code=201)
async def create_transfer(payload: TransferRequest, user_id: str = CurrentUserId):
    return await service.create_transfer(payload, user_id)


@router.get("", response_model=list[TransactionOut], response_model_by_alias=False)
async def list_my_transactions(
    limit: int = Query(default=20, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    user_id: str = CurrentUserId,
):
    return await service.list_transactions_for_user(user_id, limit, skip)


@router.get("/{transaction_id}", response_model=TransactionOut, response_model_by_alias=False)
async def get_transaction(transaction_id: str, user_id: str = CurrentUserId):
    return await service.get_transaction_for_user(transaction_id, user_id)
