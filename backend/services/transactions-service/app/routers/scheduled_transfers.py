"""Rute protejate (JWT) pentru transferuri programate/recurente.

Doar validare (Pydantic/JWT via `CurrentUserId`) și delegare către
app/service.py — logica de business (inclusiv execuția automată, în
app/scheduler.py) trăiește acolo.

Extern (prin Gateway) acestea devin:
  POST   /api/transactions/scheduled-transfers
  GET    /api/transactions/scheduled-transfers
  DELETE /api/transactions/scheduled-transfers/{id}

NOTĂ despre prefix: gateway adaugă mereu "/transactions" ca internal_prefix
fix pentru acest serviciu (vezi backend/gateway/app/routers/proxy.py::SERVICES),
la fel ca `transfers_router` — de-asta prefixul complet e "/transactions/
scheduled-transfers", nu doar "/scheduled-transfers". Router SEPARAT de
`transfers_router` (care are GET /{transaction_id} la rădăcină sub
"/transactions") — la fel ca la accounts-service/cards.py, ca să nu existe
ambiguitate de rutare.
"""

from fastapi import APIRouter, status

from app import service
from app.models import ScheduledTransferCreate, ScheduledTransferOut
from app.security import CurrentUserId

router = APIRouter(prefix="/transactions/scheduled-transfers", tags=["scheduled-transfers"])


@router.post("", response_model=ScheduledTransferOut, response_model_by_alias=False, status_code=status.HTTP_201_CREATED)
async def create_scheduled_transfer(payload: ScheduledTransferCreate, user_id: str = CurrentUserId):
    return await service.create_scheduled_transfer(user_id, payload)


@router.get("", response_model=list[ScheduledTransferOut], response_model_by_alias=False)
async def list_scheduled_transfers(user_id: str = CurrentUserId):
    return await service.list_scheduled_transfers_for_user(user_id)


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_scheduled_transfer(schedule_id: str, user_id: str = CurrentUserId):
    await service.cancel_scheduled_transfer(schedule_id, user_id)
