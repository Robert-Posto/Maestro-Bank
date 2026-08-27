"""Logica de business a deposits-service.

Separată de routing (app/routers/deposits.py) și modele (app/models.py).
Acest modul e singurul care atinge db.deposits direct.

deposits-service NU citește niciodată direct accounts_db — orice mișcare de
bani trece prin API-ul intern al accounts-service (debit/credit pe UN cont,
rezolvarea contului după user_id+tip) — vezi
accounts-service/app/routers/internal.py.
"""

import logging
from datetime import datetime, timedelta, timezone

import httpx
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status

from app.config import settings
from app.database import get_database
from app.models import DepositOpenRequest, DepositOut
from app.rates import MIN_DEPOSIT_MINOR, get_rate

logger = logging.getLogger("deposits-service")

# RON -> "current" (contul unic RON al userului); altfel valuta, lowercase —
# exact tiparul din exchange-service/app/service.py::_account_type_for_currency.
_ACCOUNT_TYPE_FOR_CURRENCY = {"RON": "current", "EUR": "eur", "USD": "usd", "GBP": "gbp"}


def _account_type_for_currency(currency: str) -> str:
    return _ACCOUNT_TYPE_FOR_CURRENCY[currency]


async def _get_account_by_user_and_type(user_id: str, account_type: str) -> dict:
    """Rezolvă contul userului pt o monedă dată — vezi
    accounts-service/app/service.py::get_account_by_user_and_type."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.get(
                f"{settings.accounts_service_url}/internal/accounts/by-user-and-type/{user_id}/{account_type}"
            )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail="accounts-service indisponibil."
            ) from exc
    if response.status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nu ai încă un cont pentru moneda asta — deschide unul din pagina Conturi înainte de a face un depozit.",
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


def _compute_interest_minor(principal_minor: int, rate_percent_annual: float, term_months: int) -> int:
    """Dobândă simplă, plătită la scadență — vezi spec-ul, secțiunea
    "Modelul unui depozit". NU compusă, NU plătită lunar."""
    return round(principal_minor * rate_percent_annual / 100 * term_months / 12)


def _to_deposit_out(doc: dict) -> DepositOut:
    return DepositOut(
        id=str(doc["_id"]),
        currency=doc["currency"],
        principal_minor=doc["principal_minor"],
        term_months=doc["term_months"],
        rate_percent_annual=doc["rate_percent_annual"],
        interest_minor=_compute_interest_minor(doc["principal_minor"], doc["rate_percent_annual"], doc["term_months"]),
        opened_at=doc["opened_at"],
        matures_at=doc["matures_at"],
        renew_at_maturity=doc["renew_at_maturity"],
        status=doc["status"],
        renewed_into_deposit_id=doc.get("renewed_into_deposit_id"),
        renewed_from_deposit_id=doc.get("renewed_from_deposit_id"),
    )


async def open_deposit(user_id: str, payload: DepositOpenRequest) -> DepositOut:
    if payload.amount_minor < MIN_DEPOSIT_MINOR[payload.currency]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Suma minimă pentru un depozit în {payload.currency} este "
            f"{MIN_DEPOSIT_MINOR[payload.currency] / 100:.2f} {payload.currency}.",
        )

    account_type = _account_type_for_currency(payload.currency)
    source_account = await _get_account_by_user_and_type(user_id, account_type)
    await _debit_account(source_account["id"], payload.amount_minor)

    now = datetime.now(timezone.utc)
    rate = get_rate(payload.currency, payload.term_months)
    doc = {
        "user_id": user_id,
        "currency": payload.currency,
        "principal_minor": payload.amount_minor,
        "term_months": payload.term_months,
        "rate_percent_annual": rate,
        "opened_at": now,
        "matures_at": now + timedelta(days=30 * payload.term_months),
        "renew_at_maturity": payload.renew_at_maturity,
        "status": "active",
        "source_account_id": source_account["id"],
        "renewed_into_deposit_id": None,
        "renewed_from_deposit_id": None,
    }
    result = await get_database().deposits.insert_one(doc)
    doc["_id"] = result.inserted_id
    logger.info(
        "deposits-service: depozit deschis (id=%s, user_id=%s, %s %s, %s luni)",
        result.inserted_id,
        user_id,
        payload.amount_minor,
        payload.currency,
        payload.term_months,
    )
    return _to_deposit_out(doc)


async def list_my_deposits(user_id: str) -> list[DepositOut]:
    cursor = get_database().deposits.find({"user_id": user_id}).sort("opened_at", -1)
    docs = await cursor.to_list(length=200)
    return [_to_deposit_out(doc) for doc in docs]


async def _get_own_active_deposit(deposit_id: str, user_id: str) -> dict:
    try:
        oid = ObjectId(deposit_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Depozit inexistent.") from exc
    doc = await get_database().deposits.find_one({"_id": oid, "user_id": user_id})
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Depozit inexistent.")
    if doc["status"] != "active":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Depozitul nu mai este activ.")
    return doc
