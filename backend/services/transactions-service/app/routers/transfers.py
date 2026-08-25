"""Rute protejate (JWT) ale transactions-service.

Doar validare (Pydantic/JWT via `CurrentUserId`) și delegare către
app/service.py — logica de business trăiește acolo.

Extern (prin Gateway) acestea devin:
  POST  /api/transactions/transfers
  GET   /api/transactions
  GET   /api/transactions/export
  GET   /api/transactions/analytics/spending
  GET   /api/transactions/analytics/cash-flow
  GET   /api/transactions/analytics/forecast
  GET   /api/transactions/{id}
  PATCH /api/transactions/{id}/recognize
  POST  /api/transactions/{id}/report
  POST  /api/transactions/{id}/hold/cancel

ORDINE IMPORTANTĂ: rutele cu path literal (/export, /analytics/*) trebuie
înregistrate ÎNAINTE de GET /{transaction_id} (wildcard cu UN SINGUR
segment) — altfel acesta le-ar "înghiți" (ex. "export" interpretat ca
transaction_id). /{transaction_id}/recognize, /{transaction_id}/report și
/{transaction_id}/hold/cancel au 2+ segmente, deci nu sunt de fapt ambigue
cu wildcard-ul de 1 segment, dar păstrăm ordinea oricum, pentru claritate.
"""

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response

from app import service
from app.models import (
    DescriptionCheckRequest,
    DescriptionCheckResponse,
    ReportTransactionRequest,
    TransactionFilters,
    TransactionOut,
    TransferRequest,
)
from app.security import CurrentUserId

router = APIRouter(prefix="/transactions", tags=["transactions"])


def get_transaction_filters(
    search: str | None = Query(default=None),
    direction: str | None = Query(default=None),
    category: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    min_amount_minor: int | None = Query(default=None, ge=0),
    max_amount_minor: int | None = Query(default=None, ge=0),
    account_id: str | None = Query(default=None),
) -> TransactionFilters:
    """Dependency FastAPI: adună parametrii de query GET într-un
    `TransactionFilters` — folosit atât de listare, cât și de export,
    astfel încât cele două să filtreze mereu IDENTIC.
    """
    return TransactionFilters(
        search=search,
        direction=direction,  # type: ignore[arg-type]
        category=category,
        date_from=date_from,
        date_to=date_to,
        min_amount_minor=min_amount_minor,
        max_amount_minor=max_amount_minor,
        account_id=account_id,
    )


@router.post("/transfers", response_model=TransactionOut, response_model_by_alias=False, status_code=201)
async def create_transfer(payload: TransferRequest, background_tasks: BackgroundTasks, user_id: str = CurrentUserId):
    return await service.create_transfer(payload, user_id, background_tasks)


@router.post("/transfers/screen-description", response_model=DescriptionCheckResponse)
async def screen_description(payload: DescriptionCheckRequest, user_id: str = CurrentUserId):
    """Verificare LIVE, apelată de frontend pe măsură ce userul scrie
    descrierea (debounced — vezi features/transfers/transfers.ts) — ÎNAINTE
    de a trimite transferul, nu doar după. `user_id` e cerut DOAR pentru
    autentificare (nu accesează niciun cont) — la fel ca restul rutelor
    protejate din acest router, tocmai ca să nu poată fi apelată neautentificat."""
    warning = service.check_description_content(payload.description)
    return DescriptionCheckResponse(warning=warning)


@router.get("", response_model=list[TransactionOut], response_model_by_alias=False)
async def list_my_transactions(
    limit: int = Query(default=20, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    filters: TransactionFilters = Depends(get_transaction_filters),
    user_id: str = CurrentUserId,
):
    return await service.list_transactions_for_user(user_id, limit, skip, filters)


@router.get("/export")
async def export_my_transactions(
    filters: TransactionFilters = Depends(get_transaction_filters), user_id: str = CurrentUserId
):
    csv_content = await service.export_transactions_csv(user_id, filters)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=maestrobank-tranzactii.csv"},
    )


@router.get("/analytics/spending")
async def spending_analytics(user_id: str = CurrentUserId):
    return await service.get_spending_analytics(user_id)


@router.get("/analytics/cash-flow")
async def cash_flow_analytics(days: int = Query(default=30, ge=7, le=90), user_id: str = CurrentUserId):
    return await service.get_cash_flow_analytics(user_id, days)


@router.get("/analytics/forecast")
async def forecast_analytics(user_id: str = CurrentUserId):
    return await service.get_forecast_analytics(user_id)


@router.get("/{transaction_id}", response_model=TransactionOut, response_model_by_alias=False)
async def get_transaction(transaction_id: str, user_id: str = CurrentUserId):
    return await service.get_transaction_for_user(transaction_id, user_id)


@router.patch("/{transaction_id}/recognize", response_model=TransactionOut, response_model_by_alias=False)
async def recognize_transaction(transaction_id: str, user_id: str = CurrentUserId):
    return await service.recognize_transaction(transaction_id, user_id)


@router.post("/{transaction_id}/report", response_model=TransactionOut, response_model_by_alias=False)
async def report_transaction(
    transaction_id: str,
    payload: ReportTransactionRequest = ReportTransactionRequest(),
    user_id: str = CurrentUserId,
):
    return await service.report_transaction(transaction_id, user_id, payload)


@router.post("/{transaction_id}/hold/cancel", response_model=TransactionOut, response_model_by_alias=False)
async def cancel_hold(transaction_id: str, user_id: str = CurrentUserId):
    return await service.cancel_own_hold(transaction_id, user_id)
