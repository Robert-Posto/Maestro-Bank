"""Verificarea de eligibilitate pentru un credit — pe date REALE ale
userului (istoricul lui de tranzacții), nu aprobare oarbă.

Regulă simplă, documentată — NU un algoritm de scoring sofisticat (aceeași
filosofie ca bufferul de siguranță din ai-orchestrator-service/app/services/
affordability_service.py, care are explicit comentariul "NU inventa un
algoritm financiar sofisticat"):

    venit_mediu_lunar = suma tranzacțiilor cu category="income" din
                         ultimele INCOME_LOOKBACK_DAYS zile / 3
    rata_lunară_nouă + suma ratelor creditelor deja active
        <= venit_mediu_lunar * MAX_INSTALLMENT_PERCENT_OF_INCOME / 100

Politică MaestroBank (prag DTI conservator, documentat ca atare — nu vine
dintr-un standard extern).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import HTTPException, status

from app.config import settings
from app.i18n import format_ron, translate

INCOME_LOOKBACK_DAYS = 90
MAX_INSTALLMENT_PERCENT_OF_INCOME = 40.0


@dataclass
class EligibilityResult:
    average_monthly_income_minor: int
    max_affordable_installment_minor: int
    existing_installments_minor: int


async def _fetch_recent_transactions(user_id: str) -> list[dict]:
    """Istoric BRUT al userului, la fel ca budgets-service::_fetch_user_transactions
    — pull, nu push, prin ruta internă deja existentă a transactions-service.
    Best-effort NU se aplică aici (spre deosebire de notificări) — dacă
    transactions-service e jos, nu putem evalua eligibilitatea corect, deci
    cererea eșuează explicit (502), nu aprobă orbește."""
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(
                f"{settings.transactions_service_url}/internal/transactions/by-user/{user_id}",
                params={"limit": 1000},
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=translate("transactionsServiceUnavailable")
        ) from exc
    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=translate("transactionsServiceQueryError")
        )
    return response.json()


def _parse_utc(value: str) -> datetime:
    """`created_at` vine din JSON-ul transactions-service — Mongo/Motor
    întoarce datetime-uri NAIVE la citire (deși au fost scrise ca UTC), deci
    Pydantic le serializează FĂRĂ sufix de fus orar (nici "Z", nici offset).
    Parsăm ce vine (cu SAU fără "Z") și, dacă rezultatul e naiv, îl tratăm
    ca UTC explicit — altfel comparația cu un datetime aware pică cu
    TypeError."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _average_monthly_income_minor(transactions: list[dict]) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=INCOME_LOOKBACK_DAYS)
    total_income_minor = 0
    for tx in transactions:
        if tx.get("category") != "income" or tx.get("direction") != "incoming":
            continue
        created_at = _parse_utc(tx["created_at"])
        if created_at < cutoff:
            continue
        total_income_minor += tx["amount_minor"]
    return round(total_income_minor / 3)  # 90 zile ≈ 3 luni


async def evaluate_eligibility(user_id: str, existing_installments_minor: int) -> EligibilityResult:
    transactions = await _fetch_recent_transactions(user_id)
    average_monthly_income_minor = _average_monthly_income_minor(transactions)
    max_affordable_installment_minor = round(
        average_monthly_income_minor * MAX_INSTALLMENT_PERCENT_OF_INCOME / 100
    )
    return EligibilityResult(
        average_monthly_income_minor=average_monthly_income_minor,
        max_affordable_installment_minor=max_affordable_installment_minor,
        existing_installments_minor=existing_installments_minor,
    )


def render_rejection_reason(result: EligibilityResult, requested_installment_minor: int) -> str:
    """Text determinist (motivul EXACT de respingere), tradus după limba
    request-ului — vezi app/i18n.py."""
    if result.average_monthly_income_minor <= 0:
        return translate("rejectNoIncomeHistory", days=INCOME_LOOKBACK_DAYS)
    available = result.max_affordable_installment_minor - result.existing_installments_minor
    return translate(
        "rejectInstalmentTooHigh",
        instalment=format_ron(requested_installment_minor),
        income=format_ron(result.average_monthly_income_minor),
        percent=f"{MAX_INSTALLMENT_PERCENT_OF_INCOME:.0f}",
        available=format_ron(max(available, 0)),
    )
