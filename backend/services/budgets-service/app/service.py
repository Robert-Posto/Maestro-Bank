"""Logica de business a budgets-service.

Separată de routing (`app/routers/*.py`, care doar validează input-ul și
deleagă aici) și de modele (`app/models.py`). Acest modul e singurul care
atinge `db.budgets` / `db.subscriptions` direct.
"""

import logging
from collections import defaultdict
from datetime import datetime, timezone

import httpx
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status

from app.config import settings
from app.database import get_database
from app.i18n import translate
from app.models import BudgetCreate, BudgetUpdate, SubscriptionCreate, SubscriptionUpdate

logger = logging.getLogger("budgets-service")


# --- Budgets ---------------------------------------------------------------


async def create_budget(user_id: str, payload: BudgetCreate) -> dict:
    db = get_database()
    doc = {
        "user_id": user_id,
        "name": payload.name,
        "category": payload.category,
        "limit_minor": payload.limit_minor,
        "period": payload.period,
        "active": True,
        "created_at": datetime.now(timezone.utc),
    }
    result = await db.budgets.insert_one(doc)
    return await db.budgets.find_one({"_id": result.inserted_id})


async def list_budgets_for_user(user_id: str) -> list[dict]:
    db = get_database()
    cursor = db.budgets.find({"user_id": user_id}).sort("created_at", -1)
    return await cursor.to_list(length=200)


async def _get_budget_for_user(budget_id: str, user_id: str) -> dict:
    db = get_database()
    try:
        object_id = ObjectId(budget_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=translate("invalidBudgetId")) from exc

    doc = await db.budgets.find_one({"_id": object_id})
    if doc is None or doc["user_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=translate("budgetNotFound"))
    return doc


async def update_budget(budget_id: str, user_id: str, payload: BudgetUpdate) -> dict:
    db = get_database()
    doc = await _get_budget_for_user(budget_id, user_id)

    updates = {key: value for key, value in payload.model_dump(exclude_unset=True).items() if value is not None}
    if updates:
        await db.budgets.update_one({"_id": doc["_id"]}, {"$set": updates})
    return await db.budgets.find_one({"_id": doc["_id"]})


async def delete_budget(budget_id: str, user_id: str) -> None:
    doc = await _get_budget_for_user(budget_id, user_id)
    db = get_database()
    await db.budgets.delete_one({"_id": doc["_id"]})


# --- Subscriptions -----------------------------------------------------------


async def create_subscription(user_id: str, payload: SubscriptionCreate) -> dict:
    db = get_database()
    doc = {
        "user_id": user_id,
        "name": payload.name,
        "amount_minor": payload.amount_minor,
        "currency": payload.currency.upper(),
        "billing_day": payload.billing_day,
        "category": payload.category,
        "active": True,
        "created_at": datetime.now(timezone.utc),
    }
    result = await db.subscriptions.insert_one(doc)
    return await db.subscriptions.find_one({"_id": result.inserted_id})


async def list_subscriptions_for_user(user_id: str) -> list[dict]:
    db = get_database()
    cursor = db.subscriptions.find({"user_id": user_id}).sort("billing_day", 1)
    return await cursor.to_list(length=200)


async def _get_subscription_for_user(subscription_id: str, user_id: str) -> dict:
    db = get_database()
    try:
        object_id = ObjectId(subscription_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=translate("invalidSubscriptionId")) from exc

    doc = await db.subscriptions.find_one({"_id": object_id})
    if doc is None or doc["user_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=translate("subscriptionNotFound"))
    return doc


async def update_subscription(subscription_id: str, user_id: str, payload: SubscriptionUpdate) -> dict:
    db = get_database()
    doc = await _get_subscription_for_user(subscription_id, user_id)

    updates = {key: value for key, value in payload.model_dump(exclude_unset=True).items() if value is not None}
    if updates:
        await db.subscriptions.update_one({"_id": doc["_id"]}, {"$set": updates})
    return await db.subscriptions.find_one({"_id": doc["_id"]})


async def delete_subscription(subscription_id: str, user_id: str) -> None:
    doc = await _get_subscription_for_user(subscription_id, user_id)
    db = get_database()
    await db.subscriptions.delete_one({"_id": doc["_id"]})


# --- Rute interne (transactions-service -> forecast) -----------------------


async def get_active_subscriptions_for_user_internal(user_id: str) -> list[dict]:
    db = get_database()
    cursor = db.subscriptions.find({"user_id": user_id, "active": True}).sort("billing_day", 1)
    docs = await cursor.to_list(length=200)
    return [
        {"name": doc["name"], "amount_minor": doc["amount_minor"], "billing_day": doc["billing_day"], "active": True}
        for doc in docs
    ]


# --- Detecție pasivă de abonamente (sugestii, din istoricul de tranzacții) --
#
# Heuristic determinist, NU ML — aceeași filozofie ca content_screening.py
# din transactions-service: rezultat instant, verificabil, ușor de explicat
# ("de ce mi-a sugerat asta?" -> "pentru că a văzut N plăți la cadență
# lunară, sumă aproape identică"). O sugestie NU devine automat abonament —
# userul confirmă explicit (POST /subscriptions, reutilizat ca la creare
# manuală), exact ca la orice altă acțiune care implică bani/date ale lui.

_MIN_OCCURRENCES = 2
_AMOUNT_TOLERANCE = 0.1  # ±10% — un abonament poate avea taxe/conversii ușor variabile
_MIN_GAP_DAYS = 20
_MAX_GAP_DAYS = 40


def _parse_transaction_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


async def _fetch_user_transactions(user_id: str) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(f"{settings.transactions_service_url}/internal/transactions/by-user/{user_id}")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError:
        logger.warning("budgets-service: nu am putut prelua tranzacțiile userului %s pentru detecție.", user_id)
        return []


async def detect_recurring_payments(user_id: str) -> list[dict]:
    """Grupează plățile de ieșire, reușite, după descriere normalizată —
    userul recunoaște un abonament după numele comerciantului ("Netflix"),
    nu după IBAN-ul lui, deci descrierea e cheia de grupare potrivită, nu
    contrapartida brută. Un grup devine sugestie doar dacă are cel puțin
    2 apariții, sumă aproape identică ȘI cadență lunară reală (20-40 zile
    între FIECARE pereche consecutivă, nu doar în medie) — pragurile astea
    țin rata de fals-pozitive mică (ex. 2 cumpărături întâmplătoare de la
    același magazin, la 3 zile distanță, NU trec)."""
    transactions = await _fetch_user_transactions(user_id)

    groups: dict[str, list[dict]] = defaultdict(list)
    for tx in transactions:
        description = (tx.get("description") or "").strip()
        if not description or tx.get("direction") != "outgoing" or tx.get("status") != "completed":
            continue
        groups[description.lower()].append(tx)

    existing = await list_subscriptions_for_user(user_id)
    existing_names = {doc["name"].strip().lower() for doc in existing}

    suggestions: list[dict] = []
    for description_key, txs in groups.items():
        if len(txs) < _MIN_OCCURRENCES:
            continue

        txs_sorted = sorted(txs, key=lambda t: t["created_at"])
        amounts = [t["amount_minor"] for t in txs_sorted]
        avg_amount = sum(amounts) / len(amounts)
        if avg_amount <= 0 or any(abs(a - avg_amount) / avg_amount > _AMOUNT_TOLERANCE for a in amounts):
            continue

        dates = [_parse_transaction_datetime(t["created_at"]) for t in txs_sorted]
        gaps_days = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        if not gaps_days or any(not (_MIN_GAP_DAYS <= gap <= _MAX_GAP_DAYS) for gap in gaps_days):
            continue

        latest = txs_sorted[-1]
        display_name = (latest.get("counterparty_name") or latest["description"]).strip()
        if display_name.lower() in existing_names:
            continue

        suggestions.append(
            {
                "name": display_name,
                "amount_minor": round(avg_amount),
                "currency": latest.get("currency", "RON"),
                "billing_day": dates[-1].day,
                "occurrences": len(txs_sorted),
                "last_seen": latest["created_at"],
            }
        )

    suggestions.sort(key=lambda s: s["occurrences"], reverse=True)
    return suggestions
