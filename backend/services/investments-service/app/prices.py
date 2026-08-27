"""Client pentru prețuri de piață — endpoint-ul NEOFICIAL Yahoo Finance
(`https://query1.finance.yahoo.com/v8/finance/chart/{symbol}`).

NOTĂ IMPORTANTĂ, spre deosebire de exchange-service/app/bnr_rates.py (care
ia cursul de la un feed OFICIAL, public, al Băncii Naționale): NU există un
echivalent gratuit, fără cheie, oficial pentru cotații bursiere live.
Endpoint-ul ăsta e NEoficial — poate fi schimbat/blocat de Yahoo oricând,
fără preaviz (verificat funcțional live la implementare — vezi
docs/superpowers/specs/2026-08-27-investments-design.md). De-aia
`refresh_all_prices` NU aruncă la primul simbol eșuat — încearcă fiecare
independent și lasă cache-ul vechi neatins pentru cele care eșuează, în loc
să lase tot portofoliul fără preț din cauza unui singur simbol picat.

Un header User-Agent explicit e necesar — Yahoo respinge unele cereri fără
el (verificat live).
"""

import logging
from datetime import datetime, timezone

import httpx

from app.catalog import SYMBOLS, name_for
from app.database import get_database

logger = logging.getLogger("investments-service")

_YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_HEADERS = {"User-Agent": "Mozilla/5.0 (MaestroBank demo; +https://maestrobank.example)"}


async def _fetch_price_minor(symbol: str) -> int:
    """Întoarce prețul curent, în cenți USD. Aruncă orice excepție
    httpx/parsare către apelant — decizia despre fallback NU se ia aici
    (vezi refresh_all_prices)."""
    async with httpx.AsyncClient(timeout=8.0, headers=_HEADERS, follow_redirects=True) as client:
        response = await client.get(_YAHOO_URL.format(symbol=symbol))
        response.raise_for_status()

    body = response.json()
    result = body.get("chart", {}).get("result")
    if not result:
        error = body.get("chart", {}).get("error") or {}
        raise ValueError(f"Yahoo n-a întors date pentru '{symbol}': {error.get('description', 'necunoscut')}.")

    price = result[0]["meta"]["regularMarketPrice"]
    return round(price * 100)


async def refresh_all_prices() -> int:
    """Reîmprospătează cache-ul pentru TOATE simbolurile din catalog —
    apelat la pornire și periodic (vezi app/scheduler.py). Întoarce câte
    simboluri au fost actualizate cu succes."""
    db = get_database()
    now = datetime.now(timezone.utc)
    updated = 0

    for symbol in SYMBOLS:
        try:
            price_minor = await _fetch_price_minor(symbol)
        except Exception:
            logger.warning("investments-service: nu am putut reîmprospăta prețul pentru %s — păstrez ultima valoare cunoscută", symbol)
            continue

        await db.price_cache.update_one(
            {"_id": symbol},
            {"$set": {"name": name_for(symbol), "price_minor": price_minor, "updated_at": now, "source": "yahoo"}},
            upsert=True,
        )
        updated += 1

    return updated


async def get_cached_price(symbol: str) -> dict | None:
    """Documentul din price_cache pentru un simbol, sau None dacă nu a
    fost încă populat (ex. primul boot, înainte de primul refresh)."""
    return await get_database().price_cache.find_one({"_id": symbol})


async def list_cached_prices() -> list[dict]:
    cursor = get_database().price_cache.find({})
    return await cursor.to_list(length=len(SYMBOLS) + 5)
