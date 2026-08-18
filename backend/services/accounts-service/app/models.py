"""Modele Pydantic pentru accounts-service (accounts_db)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# --- Core banking --------------------------------------------------------


class AccountOut(BaseModel):
    """Reprezentare completă a unui document `accounts` (uz intern/provisioning)."""

    id: str = Field(alias="_id")
    user_id: str
    iban: str
    currency: str
    balance_minor: int
    status: str
    created_at: datetime

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("id", "user_id", mode="before")
    @classmethod
    def convert_object_id(cls, value: Any) -> str:
        return str(value)


class AccountPublicOut(BaseModel):
    """DTO expus prin GET /accounts/me și GET /accounts/{id}.

    `balance` e doar pentru convenience în UI — valoarea CANONICĂ rămâne
    `balance_minor` (întreg, în bani, NU float).
    """

    id: str
    iban: str
    currency: str
    balance_minor: int
    balance: str
    status: str


class CardOut(BaseModel):
    id: str = Field(alias="_id")
    user_id: str
    account_id: str
    last_four: str
    expiry_month: int
    expiry_year: int
    status: str
    type: str
    created_at: datetime

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("id", "user_id", "account_id", mode="before")
    @classmethod
    def convert_object_id(cls, value: Any) -> str:
        return str(value)


class DevFundRequest(BaseModel):
    """STRICT development-only — vezi routers/accounts.py::dev_fund_account."""

    amount_minor: int = Field(gt=0, le=100_000_000)  # cap defensiv: max 1.000.000,00 RON/apel


# --- Rute INTERNE (service-to-service, nu trec prin Gateway) -------------


class ProvisionRequest(BaseModel):
    user_id: str


class ProvisionResponse(BaseModel):
    account: AccountOut
    card: CardOut

    model_config = ConfigDict(populate_by_name=True)


class InternalAccountView(BaseModel):
    """Reprezentare simplificată, pentru consum de către alte servicii (ex. transactions-service)."""

    id: str
    user_id: str
    iban: str
    currency: str
    balance_minor: int
    status: str


class InternalTransferRequest(BaseModel):
    from_account_id: str
    to_account_id: str
    amount_minor: int = Field(gt=0)


class InternalTransferResponse(BaseModel):
    from_balance_minor: int
    to_balance_minor: int
