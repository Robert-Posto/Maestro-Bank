"""Logica de business a investments-service.

Separată de routing (app/routers/investments.py) și modele (app/models.py).
Acest modul e singurul care atinge db.holdings direct.

investments-service NU citește niciodată direct accounts_db — orice mișcare
de bani trece prin API-ul intern al accounts-service (debit/credit pe UN
cont, rezolvarea contului după user_id+tip) — ACELEAȘI primitive GENERICE
construite pentru deposits-service (vezi accounts-service/app/routers/
internal.py), reutilizate identic aici, fără nicio modificare.
"""

import logging

import httpx
from fastapi import HTTPException, status

from app.catalog import SYMBOLS, is_valid_symbol, name_for
from app.config import settings
from app.database import get_database
from app.models import BuyRequest, HoldingOut, InstrumentOut, SellRequest
from app.prices import get_cached_price, list_cached_prices

logger = logging.getLogger("investments-service")

# Toate instrumentele din catalog se tranzacționează în USD — vezi
# docs/superpowers/specs/2026-08-27-investments-design.md.
_TRADING_ACCOUNT_TYPE = "usd"

# Sub acest prag (relativ, nu absolut) considerăm o poziție "închisă" —
# eroare de rotunjire float, nu o cantitate reală rămasă.
_QUANTITY_EPSILON = 1e-9


async def _get_usd_account(user_id: str) -> dict:
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.get(
                f"{settings.accounts_service_url}/internal/accounts/by-user-and-type/{user_id}/{_TRADING_ACCOUNT_TYPE}"
            )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail="accounts-service indisponibil."
            ) from exc
    if response.status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nu ai încă un cont USD — deschide unul din pagina Conturi înainte de a investi.",
        )
    if response.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Eroare la interogarea accounts-service.")
    return response.json()


async def _debit_account(account_id: str, amount_minor: int) -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.post(
                f"{settings.accounts_service_url}/internal/accounts/{account_id}/debit",
                json={"amount_minor": amount_minor},
            )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail="accounts-service indisponibil."
            ) from exc
    if response.status_code == 409:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Sold insuficient.")
    if response.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Eroare la debitarea contului.")


async def _credit_account(account_id: str, amount_minor: int) -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.post(
                f"{settings.accounts_service_url}/internal/accounts/{account_id}/credit",
                json={"amount_minor": amount_minor},
            )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail="accounts-service indisponibil."
            ) from exc
    if response.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Eroare la creditarea contului.")


async def _get_price_minor_or_error(symbol: str) -> int:
    cached = await get_cached_price(symbol)
    if cached is None or cached.get("price_minor") is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Prețul pentru {symbol} nu e disponibil momentan — încearcă din nou în câteva minute.",
        )
    return cached["price_minor"]


async def list_instruments() -> list[InstrumentOut]:
    cached_by_symbol = {doc["_id"]: doc for doc in await list_cached_prices()}
    return [
        InstrumentOut(
            symbol=symbol,
            name=name_for(symbol),
            price_minor=cached_by_symbol.get(symbol, {}).get("price_minor"),
            updated_at=cached_by_symbol.get(symbol, {}).get("updated_at"),
        )
        for symbol in SYMBOLS
    ]


def _to_holding_out(doc: dict, current_price_minor: int) -> HoldingOut:
    current_value_minor = round(doc["quantity"] * current_price_minor)
    cost_basis_minor = round(doc["quantity"] * doc["avg_cost_minor_per_share"])
    unrealized_gain_minor = current_value_minor - cost_basis_minor
    unrealized_gain_percent = (unrealized_gain_minor / cost_basis_minor * 100) if cost_basis_minor > 0 else 0.0
    return HoldingOut(
        symbol=doc["symbol"],
        name=name_for(doc["symbol"]),
        quantity=doc["quantity"],
        avg_cost_minor_per_share=doc["avg_cost_minor_per_share"],
        current_price_minor=current_price_minor,
        current_value_minor=current_value_minor,
        unrealized_gain_minor=unrealized_gain_minor,
        unrealized_gain_percent=round(unrealized_gain_percent, 2),
    )


async def buy(user_id: str, payload: BuyRequest) -> HoldingOut:
    if not is_valid_symbol(payload.symbol):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Simbolul '{payload.symbol}' nu este în catalog.")

    price_minor = await _get_price_minor_or_error(payload.symbol)
    account = await _get_usd_account(user_id)
    await _debit_account(account["id"], payload.amount_minor)

    quantity_bought = payload.amount_minor / price_minor

    db = get_database()
    existing = await db.holdings.find_one({"user_id": user_id, "symbol": payload.symbol})
    if existing is None:
        doc = {
            "user_id": user_id,
            "symbol": payload.symbol,
            "quantity": quantity_bought,
            "avg_cost_minor_per_share": price_minor,
        }
        await db.holdings.insert_one(doc)
    else:
        old_qty = existing["quantity"]
        old_avg = existing["avg_cost_minor_per_share"]
        new_qty = old_qty + quantity_bought
        new_avg = round((old_avg * old_qty + price_minor * quantity_bought) / new_qty)
        doc = {**existing, "quantity": new_qty, "avg_cost_minor_per_share": new_avg}
        await db.holdings.update_one(
            {"_id": existing["_id"]}, {"$set": {"quantity": new_qty, "avg_cost_minor_per_share": new_avg}}
        )

    logger.info(
        "investments-service: cumpărare (user_id=%s, symbol=%s, amount_minor=%s, quantity=%s)",
        user_id,
        payload.symbol,
        payload.amount_minor,
        quantity_bought,
    )
    return _to_holding_out(doc, price_minor)


async def sell(user_id: str, payload: SellRequest) -> HoldingOut:
    if not is_valid_symbol(payload.symbol):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Simbolul '{payload.symbol}' nu este în catalog.")

    db = get_database()
    existing = await db.holdings.find_one({"user_id": user_id, "symbol": payload.symbol})
    if existing is None or existing["quantity"] < payload.quantity - _QUANTITY_EPSILON:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Nu ai destule unități din acest simbol.")

    price_minor = await _get_price_minor_or_error(payload.symbol)
    proceeds_minor = round(payload.quantity * price_minor)

    account = await _get_usd_account(user_id)
    await _credit_account(account["id"], proceeds_minor)

    remaining_qty = existing["quantity"] - payload.quantity
    if remaining_qty <= _QUANTITY_EPSILON:
        await db.holdings.delete_one({"_id": existing["_id"]})
        remaining_qty = 0.0
    else:
        await db.holdings.update_one({"_id": existing["_id"]}, {"$set": {"quantity": remaining_qty}})

    logger.info(
        "investments-service: vânzare (user_id=%s, symbol=%s, quantity=%s, proceeds_minor=%s)",
        user_id,
        payload.symbol,
        payload.quantity,
        proceeds_minor,
    )
    doc = {**existing, "quantity": remaining_qty}
    return _to_holding_out(doc, price_minor)


async def get_portfolio(user_id: str) -> list[HoldingOut]:
    db = get_database()
    cursor = db.holdings.find({"user_id": user_id})
    docs = await cursor.to_list(length=len(SYMBOLS) + 5)

    result: list[HoldingOut] = []
    for doc in docs:
        cached = await get_cached_price(doc["symbol"])
        current_price = cached["price_minor"] if cached and cached.get("price_minor") is not None else doc["avg_cost_minor_per_share"]
        result.append(_to_holding_out(doc, current_price))
    return result
