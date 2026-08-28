"""Tool-uri de tranzacții/transferuri pentru Support Agent — apelează
EXCLUSIV /api/transactions/* prin Gateway (vezi app/tools/_gateway_client.py).
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from app.tools._gateway_client import GatewayError, gateway_request

PeriodName = Literal["today", "this_week", "this_month", "last_month", "last_7_days", "last_30_days", "last_90_days"]


async def get_transaction_details(authorization: str, transaction_id: str) -> dict[str, Any]:
    """Detaliile complete ale unei tranzacții a userului, după ID."""
    try:
        return await gateway_request("GET", f"/api/transactions/{transaction_id}", authorization)
    except GatewayError as exc:
        return {"error": exc.detail, "status_code": exc.status_code}


async def get_recent_transactions(authorization: str, limit: int = 10) -> Any:
    """Cele mai recente tranzacții ale userului (implicit 10, max 50)."""
    limit = max(1, min(int(limit), 50))
    try:
        return await gateway_request("GET", "/api/transactions", authorization, params={"limit": limit})
    except GatewayError as exc:
        return {"error": exc.detail, "status_code": exc.status_code}


def _month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    end = datetime(year + 1, 1, 1, tzinfo=timezone.utc) if month == 12 else datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return start, end


def period_bounds(period: PeriodName, now: datetime | None = None) -> tuple[datetime, datetime]:
    """Limitele EXACTE (UTC) ale unei perioade numite — calcul DETERMINIST,
    NU lăsat pe seama modelului (vezi get_transactions_by_period mai jos).

    Un LLM căruia i s-ar cere să calculeze el însuși "luna trecută" din
    data curentă greșește sistematic (confundă luna curentă cu cea
    trecută, nu gestionează corect trecerea peste an la ianuarie etc.) —
    exact bug-ul raportat de user ("luna trecută" a întors și tranzacții
    din luna curentă). `now` e parametrizabil DOAR pentru teste
    (determinism) — apelul real nu-l trimite niciodată."""
    now = now or datetime.now(timezone.utc)
    if period == "this_month":
        return _month_bounds(now.year, now.month)
    if period == "last_month":
        year, month = (now.year - 1, 12) if now.month == 1 else (now.year, now.month - 1)
        return _month_bounds(year, month)
    if period == "today":
        return datetime(now.year, now.month, now.day, tzinfo=timezone.utc), now
    if period == "this_week":
        start_date = now - timedelta(days=now.weekday())
        return datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc), now
    if period == "last_7_days":
        return now - timedelta(days=7), now
    if period == "last_30_days":
        return now - timedelta(days=30), now
    if period == "last_90_days":
        return now - timedelta(days=90), now
    raise ValueError(f"Perioadă necunoscută: {period}")


async def get_transactions_by_period(authorization: str, period: PeriodName, limit: int = 50) -> Any:
    """Tranzacțiile userului dintr-o perioadă NUMITĂ ("last_month", "this_week"
    etc.) — limitele exacte sunt calculate determinist în Python (vezi
    period_bounds), nu de model. Folosește ACEST tool, nu get_recent_transactions,
    pentru orice întrebare cu un interval de timp explicit sau implicit
    ("luna trecută", "săptămâna asta", "ultimele 30 de zile") — altfel
    modelul ar trebui să deducă el intervalul din lista brută întoarsă de
    get_recent_transactions, ceea ce duce la greșeli de calendar."""
    date_from, date_to = period_bounds(period)
    limit = max(1, min(int(limit), 100))
    try:
        return await gateway_request(
            "GET",
            "/api/transactions",
            authorization,
            params={"date_from": date_from.isoformat(), "date_to": date_to.isoformat(), "limit": limit},
        )
    except GatewayError as exc:
        return {"error": exc.detail, "status_code": exc.status_code}


async def get_transfer_status(authorization: str, transaction_id: str) -> dict[str, Any]:
    """Statusul unui transfer — identic cu get_transaction_details, pentru
    că un transfer ESTE o tranzacție (nu există o entitate "transfer"
    separată în backend). Dacă status="failed", backendul NU stochează un
    motiv explicit — agentul nu trebuie să inventeze unul (vezi system prompt)."""
    return await get_transaction_details(authorization, transaction_id)
