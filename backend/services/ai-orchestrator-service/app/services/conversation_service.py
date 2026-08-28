"""Persistență pentru conversațiile MaestroAgent (spending_forecast) și
Support Agent — un document Mongo per conversație, mesajele embedded
(conversațiile sunt scurte, deja plafonate la 40 de ture de fiecare agent
— vezi _MAX_HISTORY_MESSAGES în app/agents/spending_forecast.py și
app/agents/support.py). Vezi
docs/superpowers/specs/2026-08-26-persistent-chat-history-design.md.

Ambii agenți își păstrează logica de reasoning/tool-calling neschimbată —
routerele (app/routers/spending_forecast.py, app/routers/support.py) apelează
funcțiile de aici ÎNAINTE (încarcă istoricul) și DUPĂ (salvează tura) fiecare
apel de chat, fără să modifice deloc agenții.
"""

from datetime import datetime, timezone
from typing import Any, Literal

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status

from app.database import get_database
from app.i18n import translate

Agent = Literal["spending_forecast", "support"]

_TITLE_MAX_LENGTH = 50


def _make_title(first_message: str) -> str:
    """Titlu determinist, fără niciun apel LLM suplimentar doar pentru
    cosmetică — primele caractere ale primului mesaj, ca la orice chat
    client simplu."""
    trimmed = first_message.strip()
    if len(trimmed) <= _TITLE_MAX_LENGTH:
        return trimmed
    return trimmed[:_TITLE_MAX_LENGTH].rstrip() + "…"


def _with_utc_tzinfo(doc: dict) -> dict:
    """PyMongo/Motor decodează datetime-urile BSON ca „naive" (fără tzinfo),
    deși sunt mereu stocate în UTC (vezi `datetime.now(timezone.utc)` mai jos)
    — reatașăm tzinfo=UTC la citire ca să rămână comparabile/serializabile
    consistent cu valorile încă neserializate (ex. cele din documentul
    întors direct de `create_conversation`, înainte de orice round-trip)."""
    for key in ("created_at", "updated_at"):
        value = doc.get(key)
        if value is not None and value.tzinfo is None:
            doc[key] = value.replace(tzinfo=timezone.utc)
    for message in doc.get("messages", []):
        created_at = message.get("created_at")
        if created_at is not None and created_at.tzinfo is None:
            message["created_at"] = created_at.replace(tzinfo=timezone.utc)
    return doc


async def ensure_conversation_indexes() -> None:
    db = get_database()
    await db.conversations.create_index([("user_id", 1), ("agent", 1), ("updated_at", -1)])


async def list_conversations(user_id: str, agent: Agent) -> list[dict]:
    db = get_database()
    cursor = db.conversations.find(
        {"user_id": user_id, "agent": agent},
        {"title": 1, "updated_at": 1},
    ).sort("updated_at", -1)
    docs = await cursor.to_list(length=200)
    return [_with_utc_tzinfo(doc) for doc in docs]


async def get_conversation(user_id: str, agent: Agent, conversation_id: str) -> dict:
    db = get_database()
    try:
        object_id = ObjectId(conversation_id)
    except InvalidId as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=translate("invalidConversationId")
        ) from exc

    doc = await db.conversations.find_one({"_id": object_id})
    if doc is None or doc["user_id"] != user_id or doc["agent"] != agent:
        # 404, NU 403 — nu confirmăm că o conversație a altcuiva există.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=translate("conversationNotFound"))
    return _with_utc_tzinfo(doc)


async def create_conversation(user_id: str, agent: Agent, first_message: str) -> dict:
    db = get_database()
    now = datetime.now(timezone.utc)
    doc = {
        "user_id": user_id,
        "agent": agent,
        "title": _make_title(first_message),
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }
    result = await db.conversations.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def append_turn(conversation_id: ObjectId, user_content: str, assistant_content: str, assistant_response: dict) -> None:
    db = get_database()
    now = datetime.now(timezone.utc)
    await db.conversations.update_one(
        {"_id": conversation_id},
        {
            "$push": {
                "messages": {
                    "$each": [
                        {"role": "user", "content": user_content, "response": None, "created_at": now},
                        {
                            "role": "assistant",
                            "content": assistant_content,
                            "response": assistant_response,
                            "created_at": now,
                        },
                    ]
                }
            },
            "$set": {"updated_at": now},
        },
    )


async def delete_conversation(user_id: str, agent: Agent, conversation_id: str) -> None:
    # Reutilizează get_conversation pentru verificarea de proprietate (400
    # pe ID invalid, 404 dacă nu există/nu e a userului) — un singur loc
    # de adevăr pentru regula asta.
    conversation = await get_conversation(user_id, agent, conversation_id)
    db = get_database()
    await db.conversations.delete_one({"_id": conversation["_id"]})


def to_history_dicts(conversation: dict) -> list[dict[str, Any]]:
    """Mesajele stocate, în forma minimă cerută de agenți ca istoric
    ({role, content}) — fără `response`/`created_at`, pe care agenții nu le
    așteaptă (vezi ChatHistoryMessage din app/models/spending_forecast.py,
    ChatMessage din app/models/support.py)."""
    return [{"role": m["role"], "content": m["content"]} for m in conversation["messages"]]
