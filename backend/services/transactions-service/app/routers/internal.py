"""Rute INTERNE ale transactions-service — DOAR service-to-service /
operaționale. Gateway-ul blochează explicit orice path care începe cu
"internal/" (vezi backend/gateway/app/routers/proxy.py), deci nu sunt
accesibile din browser/Angular — la fel ca internal.py din auth-service și
accounts-service. Primul router intern al acestui serviciu.
"""

from datetime import datetime

from fastapi import APIRouter, Query

from app import service
from app.fraud.reporting import build_shadow_report
from app.models import TransactionOut

router = APIRouter(prefix="/internal/fraud", tags=["internal"])


@router.get("/shadow-report")
async def shadow_report(since: datetime | None = Query(default=None), until: datetime | None = Query(default=None)):
    """Distribuția scorurilor, rata de declanșare per regulă și tranzacțiile
    care AR FI fost reținute — folosit manual, în timpul calibrării shadow
    mode (vezi planul). Nicio colecție nouă, nicio agregare programată."""
    return await build_shadow_report(since, until)


transactions_router = APIRouter(prefix="/internal/transactions", tags=["internal"])


@transactions_router.get("/by-user/{user_id}", response_model=list[TransactionOut], response_model_by_alias=False)
async def list_transactions_by_user(user_id: str, limit: int = Query(default=300, ge=1, le=1000)):
    """Istoric BRUT al userului, pentru detecție de pattern-uri (vezi
    budgets-service::detect_recurring_payments) — NU pentru afișare directă
    către alt user. Reutilizează list_transactions_for_user, care oricum ia
    user_id ca parametru simplu (nu-l derivă din JWT) — la fel ca la
    routers/staff.py din acest serviciu."""
    return await service.list_transactions_for_user(user_id, limit, 0, include_all_statuses=True)
