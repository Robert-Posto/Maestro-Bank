"""Rute protejate (JWT) ale deposits-service.

Doar validare și delegare către app/service.py — logica de business
trăiește acolo.

Extern (prin Gateway) acestea devin:
  GET  /api/deposits/rates
  POST /api/deposits
  GET  /api/deposits
  POST /api/deposits/{id}/liquidate
"""

from fastapi import APIRouter

from app import service
from app.models import DepositOpenRequest, DepositOut, DepositRateOut
from app.rates import list_rates
from app.security import CurrentUserId

router = APIRouter(prefix="/deposits", tags=["deposits"])


@router.get("/rates", response_model=list[DepositRateOut])
async def get_rates(user_id: str = CurrentUserId):
    return list_rates()


@router.post("", response_model=DepositOut, status_code=201)
async def open_deposit_route(payload: DepositOpenRequest, user_id: str = CurrentUserId):
    return await service.open_deposit(user_id, payload)


@router.get("", response_model=list[DepositOut])
async def list_my_deposits_route(user_id: str = CurrentUserId):
    return await service.list_my_deposits(user_id)


@router.post("/{deposit_id}/liquidate", response_model=DepositOut)
async def liquidate_deposit_route(deposit_id: str, user_id: str = CurrentUserId):
    return await service.liquidate_early(deposit_id, user_id)
