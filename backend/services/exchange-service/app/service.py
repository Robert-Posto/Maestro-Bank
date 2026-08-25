"""Logica de business a exchange-service — motor FX cu curs REAL (BNR) +
politică de business SIMULATĂ (spread/comision).

Cursul de bază (mid_rate) e cel oficial publicat zilnic de Banca Națională
a României (vezi app/bnr_rates.py), cu fallback pe un curs demo static dacă
BNR e indisponibil. Formula de cost: cost total = cost de spread +
comision fix, aplicat pe suma trimisă; suma primită = (sumă - comision) /
curs aplicat.

Execuția (execute_exchange) chiar mută solduri — cheamă accounts-service
(POST /internal/accounts/exchange), care debitează contul sursă și
creditează contul destinație ale userului. Necesită ca userul să aibă deja
deschis contul pe valuta țintă (eur/usd/gbp) — la fel cum orice cont
suplimentar (economii/depozit/student) se deschide explicit, nu automat.
"""

import logging
from datetime import datetime, timezone

import httpx
from fastapi import HTTPException, status

from app.bnr_rates import fetch_bnr_rates
from app.config import (
    BASE_CURRENCY,
    DEMO_COMMISSION_MINOR,
    DEMO_MID_RATES,
    DEMO_SPREAD_PERCENT,
    SUPPORTED_FOREIGN_CURRENCIES,
    settings,
)
from app.database import get_database
from app.models import QuoteRequest

logger = logging.getLogger("exchange-service")


async def refresh_rates_from_bnr() -> bool:
    """Preia cursul zilei de la BNR și îl salvează în exchange_db.daily_rates.

    Apelat periodic dintr-un task de fundal (vezi app/main.py::lifespan).
    NU aruncă excepții către apelant — dacă BNR e indisponibil sau
    răspunde cu un format neașteptat, logăm și păstrăm cursul anterior
    (sau fallback-ul demo, dacă nu avem încă niciunul salvat).
    """
    try:
        rates, rate_date = await fetch_bnr_rates()
    except Exception as exc:  # httpx.RequestError, httpx.HTTPStatusError, ET.ParseError, ValueError
        logger.warning("exchange-service: nu am putut prelua cursul BNR (%s). Păstrez ultimul curs cunoscut.", exc)
        return False

    db = get_database()
    now = datetime.now(timezone.utc)
    for currency, mid_rate in rates.items():
        await db.daily_rates.update_one(
            {"currency": currency},
            {"$set": {"mid_rate": mid_rate, "source": "BNR", "rate_date": rate_date, "fetched_at": now}},
            upsert=True,
        )

    logger.info("exchange-service: curs BNR actualizat (data=%s, valute=%s)", rate_date, sorted(rates))
    return True


async def _get_mid_rate(currency: str) -> tuple[float, str]:
    """(curs, sursă). Prioritate: curs BNR salvat în DB -> fallback demo static."""
    db = get_database()
    doc = await db.daily_rates.find_one({"currency": currency})
    if doc is not None:
        return doc["mid_rate"], doc.get("source", "BNR")
    return DEMO_MID_RATES[currency], "demo-fallback"


async def get_current_rates() -> list[dict]:
    rates = []
    for currency in SUPPORTED_FOREIGN_CURRENCIES:
        mid_rate, source = await _get_mid_rate(currency)
        rates.append(
            {
                "currency": currency,
                "mid_rate": mid_rate,
                "spread_percent": DEMO_SPREAD_PERCENT[currency],
                "commission_minor": DEMO_COMMISSION_MINOR[currency],
                "source": source,
            }
        )
    return rates


def _foreign_currency(from_currency: str, to_currency: str) -> tuple[str, bool]:
    """Determină valuta străină implicată și direcția (RON->străină sau invers).

    Returnează (valuta_straina, is_ron_to_foreign). Aruncă 400 dacă
    perechea nu implică RON sau valuta străină nu e în dataset-ul suportat.
    """
    if from_currency == BASE_CURRENCY and to_currency in SUPPORTED_FOREIGN_CURRENCIES:
        return to_currency, True
    if to_currency == BASE_CURRENCY and from_currency in SUPPORTED_FOREIGN_CURRENCIES:
        return from_currency, False
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Pereche valutară nesuportată. Perechi disponibile: RON <-> {', '.join(SUPPORTED_FOREIGN_CURRENCIES)}.",
    )


async def compute_quote(payload: QuoteRequest) -> dict:
    foreign_currency, is_ron_to_foreign = _foreign_currency(payload.from_currency, payload.to_currency)

    mid_rate, source = await _get_mid_rate(foreign_currency)
    spread_percent = DEMO_SPREAD_PERCENT[foreign_currency]
    commission_minor = DEMO_COMMISSION_MINOR[foreign_currency]

    if is_ron_to_foreign:
        # RON -> valută străină: comisionul se scade din suma în RON
        # ÎNAINTE de conversie, apoi convertim la cursul aplicat (RON per
        # unitate valută străină). Costul total = comisionul fix + costul
        # de spread (diferența față de cursul mid), ambele în RON.
        applied_rate = round(mid_rate * (1 + spread_percent / 100), 4)
        net_ron_minor = max(payload.amount_minor - commission_minor, 0)
        received_minor = round(net_ron_minor / applied_rate)
        total_cost_minor = commission_minor + round(payload.amount_minor * spread_percent / 100)
    else:
        # valută străină -> RON: aplicăm cursul (mai mic decât mid, în
        # favoarea băncii), apoi scădem comisionul fix (în RON) din
        # rezultat.
        applied_rate = round(mid_rate * (1 - spread_percent / 100), 4)
        gross_ron_minor = round(payload.amount_minor * applied_rate)
        received_minor = max(gross_ron_minor - commission_minor, 0)
        total_cost_minor = commission_minor + round(payload.amount_minor * mid_rate * spread_percent / 100)

    total_cost_percent = round((total_cost_minor / payload.amount_minor) * 100, 2) if payload.amount_minor else 0.0

    return {
        "from_currency": payload.from_currency,
        "to_currency": payload.to_currency,
        "amount_minor": payload.amount_minor,
        "received_minor": received_minor,
        "mid_rate": mid_rate,
        "spread_percent": spread_percent,
        "applied_rate": applied_rate,
        "commission_minor": commission_minor,
        "total_cost_minor": total_cost_minor,
        "total_cost_percent": total_cost_percent,
        "source": source,
        "generated_at": datetime.now(timezone.utc),
    }


def _account_type_for_currency(currency: str) -> str:
    """RON -> "current" (contul unic RON al userului); altfel valuta
    străină, lowercase — "EUR" -> "eur" etc., exact tipurile de cont
    creabile din accounts-service (vezi acolo app/models.py::AccountType)."""
    return "current" if currency == BASE_CURRENCY else currency.lower()


async def _apply_exchange_in_accounts_service(
    user_id: str, from_currency: str, to_currency: str, debit_minor: int, credit_minor: int
) -> None:
    """Cheamă accounts-service să debiteze/crediteze efectiv soldurile —
    vezi accounts-service/app/routers/internal.py::apply_internal_exchange.
    Traduce eșecurile (404 = cont lipsă, 409 = sold insuficient) în
    HTTPException-uri cu mesajul original, transparent pentru user."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{settings.accounts_service_url}/internal/accounts/exchange",
            json={
                "user_id": user_id,
                "from_account_type": _account_type_for_currency(from_currency),
                "to_account_type": _account_type_for_currency(to_currency),
                "debit_minor": debit_minor,
                "credit_minor": credit_minor,
            },
        )

    if response.status_code == status.HTTP_404_NOT_FOUND:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=response.json().get("detail"))
    if response.status_code == status.HTTP_409_CONFLICT:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=response.json().get("detail"))
    response.raise_for_status()


async def execute_exchange(user_id: str, payload: QuoteRequest) -> dict:
    """Execută un schimb valutar REAL — mută solduri între contul RON al
    userului și contul lui pe valuta țintă (sau invers), prin
    accounts-service. Dacă userul nu are încă deschis contul pe valuta
    respectivă, accounts-service întoarce 404, tradus mai jos într-un 400
    cu mesaj clar (userul trebuie să-l deschidă întâi, din pagina Conturi)."""
    quote = await compute_quote(payload)

    await _apply_exchange_in_accounts_service(
        user_id, quote["from_currency"], quote["to_currency"], quote["amount_minor"], quote["received_minor"]
    )

    db = get_database()
    doc = {
        "user_id": user_id,
        "from_currency": quote["from_currency"],
        "to_currency": quote["to_currency"],
        "amount_minor": quote["amount_minor"],
        "received_minor": quote["received_minor"],
        "applied_rate": quote["applied_rate"],
        "commission_minor": quote["commission_minor"],
        "total_cost_minor": quote["total_cost_minor"],
        "created_at": datetime.now(timezone.utc),
    }
    result = await db.demo_exchanges.insert_one(doc)
    logger.info(
        "exchange-service: schimb executat (id=%s, user_id=%s, %s->%s, amount_minor=%s)",
        result.inserted_id,
        user_id,
        quote["from_currency"],
        quote["to_currency"],
        quote["amount_minor"],
    )
    return await db.demo_exchanges.find_one({"_id": result.inserted_id})


async def list_exchanges_for_user(user_id: str) -> list[dict]:
    db = get_database()
    cursor = db.demo_exchanges.find({"user_id": user_id}).sort("created_at", -1)
    return await cursor.to_list(length=100)
