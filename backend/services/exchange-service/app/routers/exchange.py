"""Rute protejate (JWT) ale exchange-service — schimb valutar DEMO.

Extern (prin Gateway) acestea devin:
  GET  /api/exchange/rates
  GET  /api/exchange/quote
  POST /api/exchange/demo
  GET  /api/exchange/demo/history

NOTĂ despre prefix: la fel ca accounts-service, acest router NU are
prefix propriu — gateway-ul consumă deja segmentul "exchange" ca nume de
serviciu (internal_prefix="" în backend/gateway/app/routers/proxy.py),
deci rutele interne rămân bare (/rates, /quote, /demo), fără să dubleze
"exchange" în cale.

⚠️ Simulare — vezi app/config.py și app/service.py pentru explicații.
"""

from fastapi import APIRouter, Query

from app import service
from app.models import DemoExchangeOut, QuoteOut, QuoteRequest, RateOut
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


@router.post("/demo", response_model=DemoExchangeOut, response_model_by_alias=False, status_code=201)
async def create_demo_exchange(payload: QuoteRequest, user_id: str = CurrentUserId):
    return await service.execute_demo_exchange(user_id, payload)


@router.get("/demo/history", response_model=list[DemoExchangeOut], response_model_by_alias=False)
async def get_demo_history(user_id: str = CurrentUserId):
    return await service.list_demo_exchanges_for_user(user_id)
