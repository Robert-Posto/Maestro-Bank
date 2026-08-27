"""Rute protejate (JWT) ale investments-service.

Doar validare și delegare către app/service.py — logica de business
trăiește acolo.

Extern (prin Gateway) acestea devin:
  GET  /api/investments/instruments
  GET  /api/investments/portfolio
  POST /api/investments/buy
  POST /api/investments/sell
"""

from fastapi import APIRouter

from app import service
from app.models import BuyRequest, HoldingOut, InstrumentOut, SellRequest
from app.security import CurrentUserId

router = APIRouter(prefix="/investments", tags=["investments"])


@router.get("/instruments", response_model=list[InstrumentOut])
async def get_instruments(user_id: str = CurrentUserId):
    return await service.list_instruments()


@router.get("/portfolio", response_model=list[HoldingOut])
async def get_portfolio(user_id: str = CurrentUserId):
    return await service.get_portfolio(user_id)


@router.post("/buy", response_model=HoldingOut, status_code=201)
async def buy(payload: BuyRequest, user_id: str = CurrentUserId):
    return await service.buy(user_id, payload)


@router.post("/sell", response_model=HoldingOut)
async def sell(payload: SellRequest, user_id: str = CurrentUserId):
    return await service.sell(user_id, payload)
