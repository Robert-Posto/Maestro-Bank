"""Modele Pydantic pentru budgets-service (budgets_db).

Colecții: `budgets` (limite de cheltuieli informative pe categorie) și
`subscriptions` (plăți recurente cunoscute — ex. Netflix, chirie).
Bugetul e informativ — NU blochează transferuri (vezi transactions-service,
care nu citește niciodată budgets_db).
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

BUDGET_PERIODS: list[str] = ["weekly", "monthly", "yearly"]


# --- Budgets ---------------------------------------------------------------


class BudgetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=140)
    category: str = Field(min_length=1, max_length=60)
    limit_minor: int = Field(gt=0, le=1_000_000_000)
    period: Literal["weekly", "monthly", "yearly"] = "monthly"

    @field_validator("name", "category")
    @classmethod
    def strip_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Câmpul nu poate fi gol.")
        return stripped


class BudgetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=140)
    category: str | None = Field(default=None, min_length=1, max_length=60)
    limit_minor: int | None = Field(default=None, gt=0, le=1_000_000_000)
    period: Literal["weekly", "monthly", "yearly"] | None = None
    active: bool | None = None


class BudgetOut(BaseModel):
    id: str = Field(alias="_id")
    name: str
    category: str
    limit_minor: int
    period: str
    active: bool = True
    created_at: datetime

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("id", mode="before")
    @classmethod
    def convert_object_id(cls, value: Any) -> str:
        return str(value)


# --- Subscriptions -----------------------------------------------------------


class SubscriptionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=140)
    amount_minor: int = Field(gt=0, le=1_000_000_000)
    currency: str = Field(default="RON", min_length=3, max_length=3)
    billing_day: int = Field(ge=1, le=31)
    category: str = Field(default="subscriptions", max_length=60)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Numele abonamentului nu poate fi gol.")
        return stripped


class SubscriptionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=140)
    amount_minor: int | None = Field(default=None, gt=0, le=1_000_000_000)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    billing_day: int | None = Field(default=None, ge=1, le=31)
    category: str | None = Field(default=None, max_length=60)
    active: bool | None = None


class SubscriptionOut(BaseModel):
    id: str = Field(alias="_id")
    name: str
    amount_minor: int
    currency: str = "RON"
    billing_day: int
    category: str = "subscriptions"
    active: bool = True
    created_at: datetime

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("id", mode="before")
    @classmethod
    def convert_object_id(cls, value: Any) -> str:
        return str(value)


class InternalSubscriptionView(BaseModel):
    """Reprezentare simplificată, pentru consum de către transactions-service (forecast)."""

    name: str
    amount_minor: int
    billing_day: int
    active: bool
