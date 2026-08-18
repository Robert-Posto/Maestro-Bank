"""Modele Pydantic pentru transactions-service (tx_db)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TransferRequest(BaseModel):
    """Input primit de la Angular pentru POST /transactions/transfers.

    Contul SURSĂ NU vine din input — se determină din userul autentificat
    (JWT), tocmai ca frontendul să nu poată pretinde alt cont sursă.
    """

    to_iban: str = Field(min_length=10, max_length=34)
    amount_minor: int = Field(gt=0, le=100_000_000)  # cap defensiv: max 1.000.000,00 RON/transfer
    description: str = Field(default="", max_length=140)

    @field_validator("to_iban")
    @classmethod
    def normalize_iban(cls, value: str) -> str:
        return value.strip().upper().replace(" ", "")


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
    status: str
    created_at: datetime

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("id", mode="before")
    @classmethod
    def convert_object_id(cls, value: Any) -> str:
        return str(value)
