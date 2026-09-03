"""Tool: conversie valutară REALĂ (curs BNR + politica MaestroBank de
spread/comision) — apelează GET /api/exchange/quote prin Gateway
(exchange-service în spate). Folosit de `estimate_trip_cost` (vezi
app/tools/registry.py) ca să convertească un preț de zbor Duffel (de obicei
EUR) în RON, REUTILIZÂND infrastructura de schimb valutar deja existentă în
proiect — nicio dependență externă nouă doar pentru asta.
"""

from __future__ import annotations

from app.tools._client import gateway_get


async def get_quote(from_currency: str, to_currency: str, amount_minor: int, authorization_header: str) -> dict:
    """Shape (din exchange-service, vezi app/models.py::QuoteOut):
    {from_currency, to_currency, amount_minor, received_minor, mid_rate,
    spread_percent, applied_rate, commission_minor, total_cost_minor,
    total_cost_percent}."""
    return await gateway_get(
        "exchange/quote",
        authorization_header,
        params={"from_currency": from_currency, "to_currency": to_currency, "amount_minor": amount_minor},
    )
