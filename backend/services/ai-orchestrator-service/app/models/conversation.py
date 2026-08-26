"""DTO-uri pentru endpoint-urile de conversații (listă/detaliu/ștergere) —
comune ambilor agenți, vezi app/services/conversation_service.py."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class ConversationSummary(BaseModel):
    id: str
    title: str
    updated_at: datetime


class ConversationMessageOut(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    response: dict[str, Any] | None = None
    created_at: datetime


class ConversationDetail(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[ConversationMessageOut]


def to_summary(doc: dict) -> ConversationSummary:
    return ConversationSummary(id=str(doc["_id"]), title=doc["title"], updated_at=doc["updated_at"])


def to_detail(doc: dict) -> ConversationDetail:
    return ConversationDetail(
        id=str(doc["_id"]),
        title=doc["title"],
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
        messages=[ConversationMessageOut(**m) for m in doc["messages"]],
    )
