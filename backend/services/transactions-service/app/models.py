"""Modele Pydantic pentru transactions-service (tx_db)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Categorii suportate (vezi task-ul MaestroBank, secțiunea 17). "other" e
# implicit pentru transferuri fără categorie selectată explicit de user.
TRANSACTION_CATEGORIES: list[str] = [
    "groceries",
    "shopping",
    "transport",
    "bills",
    "restaurants",
    "entertainment",
    "subscriptions",
    "income",
    "other",
]


class TransferRequest(BaseModel):
    """Input primit de la Angular pentru POST /transactions/transfers.

    Contul SURSĂ NU vine din input — se determină din userul autentificat
    (JWT), tocmai ca frontendul să nu poată pretinde alt cont sursă.
    """

    to_iban: str = Field(min_length=10, max_length=34)
    amount_minor: int = Field(gt=0, le=100_000_000)  # cap defensiv: max 1.000.000,00 RON/transfer
    description: str = Field(default="", max_length=140)
    category: str = Field(default="other")

    @field_validator("to_iban")
    @classmethod
    def normalize_iban(cls, value: str) -> str:
        return value.strip().upper().replace(" ", "")

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        normalized = (value or "other").strip().lower()
        return normalized if normalized in TRANSACTION_CATEGORIES else "other"


class TransactionOut(BaseModel):
    """DTO orientat pe VIEWER — `direction`/`counterparty_iban` sunt
    calculate relativ la contul userului care face requestul, nu sunt un
    câmp brut din baza de date.
    """

    id: str = Field(alias="_id")
    direction: Literal["incoming", "outgoing"]
    amount_minor: int
    amount: str
    currency: str
    counterparty_iban: str
    description: str
    category: str = "other"
    status: str
    recognized: bool = False
    reported: bool = False
    created_at: datetime

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("id", mode="before")
    @classmethod
    def convert_object_id(cls, value: Any) -> str:
        return str(value)


class TransactionFilters(BaseModel):
    """Query params suportați de GET /transactions și GET /transactions/export."""

    search: str | None = None
    direction: Literal["incoming", "outgoing"] | None = None
    category: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    min_amount_minor: int | None = Field(default=None, ge=0)
    max_amount_minor: int | None = Field(default=None, ge=0)
    account_id: str | None = None


class ReportTransactionRequest(BaseModel):
    reason: str = Field(default="", max_length=280)
