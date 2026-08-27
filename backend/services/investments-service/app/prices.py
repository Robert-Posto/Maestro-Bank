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

from app.catalog import ALL_SYMBOLS, name_for
from app.database import get_database

logger = logging.getLogger("investments-service")

_YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_HEADERS = {"User-Agent": "Mozilla/5.0 (MaestroBank demo; +https://maestrobank.example)"}


async def _fetch_chart_result(symbol: str, *, range_: str | None = None, interval: str = "1d") -> dict:
    """Un singur apel către endpoint-ul "chart" al Yahoo — folosit ATÂT
    pentru prețul simplu (fără range_, doar `meta`) CÂT ȘI pentru detalii +
    istoric (cu range_, `meta` + `timestamp`/`indicators.quote[0].close`) —
    e ACELAȘI endpoint, doar cu parametri diferiți, nu are sens un al
    doilea client HTTP separat pentru fiecare caz."""
    params = {"range": range_, "interval": interval} if range_ else None
    async with httpx.AsyncClient(timeout=8.0, headers=_HEADERS, follow_redirects=True) as client:
        response = await client.get(_YAHOO_URL.format(symbol=symbol), params=params)
        response.raise_for_status()

    body = response.json()
    result = body.get("chart", {}).get("result")
    if not result:
        error = body.get("chart", {}).get("error") or {}
        raise ValueError(f"Yahoo n-a întors date pentru '{symbol}': {error.get('description', 'necunoscut')}.")
    return result[0]


async def refresh_all_prices() -> int:
    """Reîmprospătează cache-ul pentru TOATE simbolurile — catalogul
    tranzacționabil ȘI indicii bursieri (ambii au nevoie de preț +
    variație zilnică pentru afișare) — apelat la pornire și periodic (vezi
    app/scheduler.py). Întoarce câte simboluri au fost actualizate cu succes."""
    db = get_database()
    now = datetime.now(timezone.utc)
    updated = 0

    for symbol in ALL_SYMBOLS:
        try:
            result = await _fetch_chart_result(symbol)
            meta = result["meta"]
            price_minor = round(meta["regularMarketPrice"] * 100)
            previous_close_minor = round(meta.get("previousClose", meta["regularMarketPrice"]) * 100)
        except Exception:
            logger.warning(
                "investments-service: nu am putut reîmprospăta prețul pentru %s — păstrez ultima valoare cunoscută",
                symbol,
            )
            continue

        await db.price_cache.update_one(
            {"_id": symbol},
            {
                "$set": {
                    "name": name_for(symbol),
                    "price_minor": price_minor,
                    "previous_close_minor": previous_close_minor,
                    "updated_at": now,
                    "source": "yahoo",
                }
            },
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
    return await cursor.to_list(length=len(ALL_SYMBOLS) + 5)


async def fetch_detail(symbol: str, range_: str = "1mo") -> dict:
    """Detalii complete + istoric de preț — pentru vizualizarea la click
    (vezi GET /investments/instruments/{symbol}/detail). NU e cache-uit —
    apelat rar (doar când userul chiar deschide detaliile unui instrument),
    spre deosebire de refresh_all_prices (apelat periodic, pentru toată
    lista)."""
    result = await _fetch_chart_result(symbol, range_=range_)
    meta = result["meta"]
    price = meta["regularMarketPrice"]

    timestamps = result.get("timestamp") or []
    closes = (result.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
    history = [
        {"date": datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat(), "price_minor": round(close * 100)}
        for ts, close in zip(timestamps, closes)
        if close is not None
    ]

    return {
        "price_minor": round(price * 100),
        "previous_close_minor": round(meta.get("previousClose", price) * 100),
        "day_high_minor": round(meta.get("regularMarketDayHigh", price) * 100),
        "day_low_minor": round(meta.get("regularMarketDayLow", price) * 100),
        "week52_high_minor": round(meta.get("fiftyTwoWeekHigh", price) * 100),
        "week52_low_minor": round(meta.get("fiftyTwoWeekLow", price) * 100),
        "volume": meta.get("regularMarketVolume"),
        "history": history,
    }
