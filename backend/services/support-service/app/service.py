"""Logica de business a support-service.

Separată de routing (`app/routers/support.py`, care doar validează
input-ul și deleagă aici) și de modele (`app/models.py`). Acest modul e
singurul care atinge `db.tickets` direct.
"""

import logging
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status

from app.database import get_database
from app.models import NotificationCreate, TicketCreate

logger = logging.getLogger("support-service")


async def create_ticket(user_id: str, payload: TicketCreate) -> dict:
    db = get_database()
    now = datetime.now(timezone.utc)
    doc = {
        "user_id": user_id,
        "subject": payload.subject,
        "category": payload.category,
        "message": payload.message,
        "status": "open",
        "created_at": now,
        "updated_at": now,
    }
    result = await db.tickets.insert_one(doc)
    logger.info("support-service: ticket creat (id=%s, user_id=%s, category=%s)", result.inserted_id, user_id, payload.category)
    return await db.tickets.find_one({"_id": result.inserted_id})


async def list_tickets_for_user(user_id: str) -> list[dict]:
    db = get_database()
    cursor = db.tickets.find({"user_id": user_id}).sort("created_at", -1)
    return await cursor.to_list(length=200)


async def get_ticket_for_user(ticket_id: str, user_id: str) -> dict:
    db = get_database()
    try:
        object_id = ObjectId(ticket_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID de tichet invalid.") from exc

    doc = await db.tickets.find_one({"_id": object_id})
    if doc is None or doc["user_id"] != user_id:
        # Nu dezvăluim că tichetul există dar nu-i aparține — 404 în ambele cazuri.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tichetul nu există.")
    return doc


# --- Notificări -------------------------------------------------------------


async def create_notification(payload: NotificationCreate) -> dict:
    """Apelat DOAR intern, de alte servicii (accounts/budgets/transactions) —
    vezi app/routers/notifications.py. Userul nu poate crea notificări direct."""
    db = get_database()
    doc = {
        "user_id": payload.user_id,
        "kind": payload.kind,
        "text": payload.text,
        "read": False,
        "created_at": datetime.now(timezone.utc),
    }
    result = await db.notifications.insert_one(doc)
    logger.info("support-service: notificare creată (user_id=%s, kind=%s)", payload.user_id, payload.kind)
    return await db.notifications.find_one({"_id": result.inserted_id})


async def list_notifications_for_user(user_id: str) -> list[dict]:
    db = get_database()
    cursor = db.notifications.find({"user_id": user_id}).sort("created_at", -1).limit(30)
    return await cursor.to_list(length=30)


async def mark_all_read(user_id: str) -> None:
    db = get_database()
    await db.notifications.update_many({"user_id": user_id, "read": False}, {"$set": {"read": True}})


async def delete_notification(notification_id: str, user_id: str) -> None:
    """Șterge o singură notificare a userului curent.

    `user_id` intră în filtrul de ștergere, nu doar într-o verificare
    ulterioară — așa nu există fereastră în care altcineva ar putea șterge
    notificarea altui user, indiferent de ce id trimite.
    """
    db = get_database()
    try:
        object_id = ObjectId(notification_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID de notificare invalid.") from exc

    result = await db.notifications.delete_one({"_id": object_id, "user_id": user_id})
    if result.deleted_count == 0:
        # Nu dezvăluim că notificarea există dar aparține altcuiva — 404 în
        # ambele cazuri, la fel ca la tichete (vezi get_ticket_for_user).
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notificarea nu există.")
