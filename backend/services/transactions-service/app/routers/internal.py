"""Rute INTERNE ale transactions-service — DOAR service-to-service /
operaționale. Gateway-ul blochează explicit orice path care începe cu
"internal/" (vezi backend/gateway/app/routers/proxy.py), deci nu sunt
accesibile din browser/Angular — la fel ca internal.py din auth-service și
accounts-service. Primul router intern al acestui serviciu.
"""

from datetime import datetime

from fastapi import APIRouter, Query

from app.fraud.reporting import build_shadow_report

router = APIRouter(prefix="/internal/fraud", tags=["internal"])


@router.get("/shadow-report")
async def shadow_report(since: datetime | None = Query(default=None), until: datetime | None = Query(default=None)):
    """Distribuția scorurilor, rata de declanșare per regulă și tranzacțiile
    care AR FI fost reținute — folosit manual, în timpul calibrării shadow
    mode (vezi planul). Nicio colecție nouă, nicio agregare programată."""
    return await build_shadow_report(since, until)
