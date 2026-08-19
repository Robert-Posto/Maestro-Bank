"""Logica de business a exchange-service — motor FX DEMO.

⚠️ Simulare, NU integrare bancară/valutară reală (vezi app/config.py).
Formula e intenționat simplă și transparentă (vezi task-ul MaestroBank,
secțiunea 15): cost total = cost de spread + comision fix, aplicat pe
suma trimisă; suma primită = (sumă - comision) / curs aplicat.
"""

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.config import (
    BASE_CURRENCY,
    DEMO_COMMISSION_MINOR,
    DEMO_MID_RATES,
    DEMO_SPREAD_PERCENT,
)
from app.database import get_database
from app.models import QuoteRequest

logger = logging.getLogger("exchange-service")


def get_demo_rates() -> list[dict]:
    return [
        {
            "currency": currency,
            "mid_rate": DEMO_MID_RATES[currency],
            "spread_percent": DEMO_SPREAD_PERCENT[currency],
            "commission_minor": DEMO_COMMISSION_MINOR[currency],
            "is_demo": True,
        }
        for currency in DEMO_MID_RATES
    ]


def _foreign_currency(from_currency: str, to_currency: str) -> tuple[str, bool]:
    """Determină valuta străină implicată și direcția (RON->străină sau invers).

    Returnează (valuta_straina, is_ron_to_foreign). Aruncă 400 dacă
    perechea nu implică RON sau valuta străină nu e în dataset-ul demo.
    """
    if from_currency == BASE_CURRENCY and to_currency in DEMO_MID_RATES:
        return to_currency, True
    if to_currency == BASE_CURRENCY and from_currency in DEMO_MID_RATES:
        return from_currency, False
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Pereche valutară nesuportată în demo. Perechi disponibile: RON <-> {', '.join(DEMO_MID_RATES)}.",
    )


def compute_quote(payload: QuoteRequest) -> dict:
    foreign_currency, is_ron_to_foreign = _foreign_currency(payload.from_currency, payload.to_currency)

    mid_rate = DEMO_MID_RATES[foreign_currency]
    spread_percent = DEMO_SPREAD_PERCENT[foreign_currency]
    commission_minor = DEMO_COMMISSION_MINOR[foreign_currency]
    applied_rate = round(mid_rate * (1 + spread_percent / 100), 4)

    if is_ron_to_foreign:
        # RON -> valută străină: comisionul se scade din suma în RON
        # ÎNAINTE de conversie, apoi convertim la cursul aplicat (RON per
        # unitate valută străină). Costul total = comisionul fix + costul
        # de spread (diferența față de cursul mid), ambele în RON.
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
        "is_demo": True,
        "generated_at": datetime.now(timezone.utc),
    }


async def execute_demo_exchange(user_id: str, payload: QuoteRequest) -> dict:
    """Înregistrează o simulare de schimb valutar. NU mută fonduri reale —
    accounts-service NU e apelat aici, intenționat (vezi task-ul
    MaestroBank, secțiunea 15: "Nu avem integrare FX reală").
    """
    quote = compute_quote(payload)

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
        "is_demo": True,
        "created_at": datetime.now(timezone.utc),
    }
    result = await db.demo_exchanges.insert_one(doc)
    logger.info(
        "exchange-service: simulare înregistrată (id=%s, user_id=%s, %s->%s, amount_minor=%s)",
        result.inserted_id,
        user_id,
        quote["from_currency"],
        quote["to_currency"],
        quote["amount_minor"],
    )
    return await db.demo_exchanges.find_one({"_id": result.inserted_id})


async def list_demo_exchanges_for_user(user_id: str) -> list[dict]:
    db = get_database()
    cursor = db.demo_exchanges.find({"user_id": user_id}).sort("created_at", -1)
    return await cursor.to_list(length=100)
