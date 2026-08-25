"""Modele Pydantic pentru exchange-service (exchange_db)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RateOut(BaseModel):
    currency: str
    mid_rate: float
    spread_percent: float
    commission_minor: int
    # "BNR" = curs oficial al zilei (Banca Națională a României);
    # "demo-fallback" = BNR indisponibil, folosim ultima valoare cunoscută.
    source: str = "BNR"


class QuoteRequest(BaseModel):
    from_currency: str = Field(min_length=3, max_length=3)
    to_currency: str = Field(min_length=3, max_length=3)
    amount_minor: int = Field(gt=0, le=1_000_000_000)

    @field_validator("from_currency", "to_currency")
    @classmethod
    def upper(cls, value: str) -> str:
        return value.strip().upper()


class QuoteOut(BaseModel):
    from_currency: str
    to_currency: str
    amount_minor: int
    received_minor: int
    mid_rate: float
    spread_percent: float
    applied_rate: float
    commission_minor: int
    total_cost_minor: int
    total_cost_percent: float
    source: str = "BNR"
    generated_at: datetime


class ExchangeOut(BaseModel):
    """Un schimb valutar EXECUTAT — vezi app/service.py::execute_exchange.
    Solduri chiar mutate (accounts-service), nu doar o simulare logată."""

    id: str = Field(alias="_id")
    from_currency: str
    to_currency: str
    amount_minor: int
    received_minor: int
    applied_rate: float
    commission_minor: int
    total_cost_minor: int
    created_at: datetime

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("id", mode="before")
    @classmethod
    def convert_object_id(cls, value: Any) -> str:
        return str(value)
