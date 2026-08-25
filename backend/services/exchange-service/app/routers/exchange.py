"""Rute protejate (JWT) ale exchange-service — schimb valutar.

Extern (prin Gateway) acestea devin:
  GET  /api/exchange/rates
  GET  /api/exchange/quote
  POST /api/exchange/execute
  GET  /api/exchange/history

NOTĂ despre prefix: la fel ca accounts-service, acest router NU are
prefix propriu — gateway-ul consumă deja segmentul "exchange" ca nume de
serviciu (internal_prefix="" în backend/gateway/app/routers/proxy.py),
deci rutele interne rămân bare (/rates, /quote, /execute), fără să dubleze
"exchange" în cale.

Cursul de bază e REAL (BNR); execuția (POST /execute) chiar mută solduri —
vezi app/service.py.
"""

from fastapi import APIRouter, Query

from app import service
from app.models import ExchangeOut, QuoteOut, QuoteRequest, RateOut
from app.security import CurrentUserId

router = APIRouter(tags=["exchange"])


@router.get("/rates", response_model=list[RateOut])
async def get_rates(user_id: str = CurrentUserId):
    return await service.get_current_rates()


@router.get("/quote", response_model=QuoteOut)
async def get_quote(
    from_currency: str = Query(..., min_length=3, max_length=3),
    to_currency: str = Query(..., min_length=3, max_length=3),
    amount_minor: int = Query(..., gt=0),
    user_id: str = CurrentUserId,
):
    payload = QuoteRequest(from_currency=from_currency, to_currency=to_currency, amount_minor=amount_minor)
    return await service.compute_quote(payload)


@router.post("/execute", response_model=ExchangeOut, response_model_by_alias=False, status_code=201)
async def execute_exchange(payload: QuoteRequest, user_id: str = CurrentUserId):
    return await service.execute_exchange(user_id, payload)


@router.get("/history", response_model=list[ExchangeOut], response_model_by_alias=False)
async def get_history(user_id: str = CurrentUserId):
    return await service.list_exchanges_for_user(user_id)
