"""Modele Pydantic pentru support-service (support_db, colecția `tickets`)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

TICKET_CATEGORIES: list[str] = ["card", "transfer", "account", "technical", "other"]
TICKET_STATUSES: list[str] = ["open", "in_progress", "resolved"]


class TicketCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=140)
    category: Literal["card", "transfer", "account", "technical", "other"] = "other"
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("subject", "message")
    @classmethod
    def strip_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Câmpul nu poate fi gol.")
        return stripped


class TicketOut(BaseModel):
    id: str = Field(alias="_id")
    subject: str
    category: str
    message: str
    status: str = "open"
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("id", mode="before")
    @classmethod
    def convert_object_id(cls, value: Any) -> str:
        return str(value)


# --- Notificări (istoric persistent, alimentat de alte servicii) ---------
#
# Vezi app/routers/notifications.py — POST /internal/notifications e apelat
# de accounts-service (card blocat), budgets-service (prag de buget atins),
# transactions-service (transfer reușit), NU direct de frontend.

NotificationKind = Literal[
    "budget", "card", "transfer", "transfer_received", "transfer_hold", "transfer_hold_cancelled", "system"
]


class NotificationCreate(BaseModel):
    """Payload-ul trimis de UN ALT serviciu, prin POST /internal/notifications."""

    user_id: str
    kind: NotificationKind
    text: str = Field(min_length=1, max_length=280)


class NotificationOut(BaseModel):
    id: str = Field(alias="_id")
    kind: str
    text: str
    read: bool
    created_at: datetime

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("id", mode="before")
    @classmethod
    def convert_object_id(cls, value: Any) -> str:
        return str(value)
