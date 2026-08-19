"""Logica de business a budgets-service.

Separată de routing (`app/routers/*.py`, care doar validează input-ul și
deleagă aici) și de modele (`app/models.py`). Acest modul e singurul care
atinge `db.budgets` / `db.subscriptions` direct.
"""

import logging
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status

from app.database import get_database
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID de buget invalid.") from exc

    doc = await db.budgets.find_one({"_id": object_id})
    if doc is None or doc["user_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bugetul nu există.")
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID de abonament invalid.") from exc

    doc = await db.subscriptions.find_one({"_id": object_id})
    if doc is None or doc["user_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Abonamentul nu există.")
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
