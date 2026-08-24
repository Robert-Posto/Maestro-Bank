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


class HoldInfoOut(BaseModel):
    """Prezent DOAR pe o tranzacție reținută (status="pending_review" sau
    care A FOST reținută) — vezi app/holds.py."""

    expires_at: datetime
    resolution: str | None = None


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
    # "Prenume Nume" al contrapărții, DOAR pentru transferuri către/de la
    # un user MaestroBank real — None pentru plăți către comercianți
    # (acolo frontendul afișează descrierea, ex. numele comerciantului).
    counterparty_name: str | None = None
    description: str
    category: str = "other"
    status: str
    recognized: bool = False
    reported: bool = False
    created_at: datetime
    hold: HoldInfoOut | None = None

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


# --- Transferuri programate/recurente --------------------------------------
#
# Diferit de detecția PASIVĂ de abonamente (budgets-service) — aici userul
# INIȚIAZĂ explicit o automatizare ("trimite 500 RON lunar către IBAN X").
# Execuția se face de un loop intern (vezi app/scheduler.py), care
# reutilizează EXACT create_transfer — nu duplică validarea/logica.

ScheduleFrequency = Literal["weekly", "monthly"]


class ScheduledTransferCreate(BaseModel):
    to_iban: str = Field(min_length=10, max_length=34)
    amount_minor: int = Field(gt=0, le=100_000_000)
    description: str = Field(default="", max_length=140)
    frequency: ScheduleFrequency

    @field_validator("to_iban")
    @classmethod
    def normalize_iban(cls, value: str) -> str:
        return value.strip().upper().replace(" ", "")


class ScheduledTransferOut(BaseModel):
    id: str = Field(alias="_id")
    to_iban: str
    amount_minor: int
    description: str
    frequency: ScheduleFrequency
    next_run_at: datetime
    active: bool
    created_at: datetime

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("id", mode="before")
    @classmethod
    def convert_object_id(cls, value: Any) -> str:
        return str(value)


# --- Personal — revizuire evaluări fraud (vezi routers/staff.py) -----------
#
# DOAR pentru personal (RequireStaff, app/security.py). Evaluarea automată
# originală (score/fired_rules/decision_would_apply) nu se schimbă NICIODATĂ
# — vezi app/fraud/staff.py::review_evaluation. O revizuire e o adnotare
# adăugată, nu o rescriere.

FraudReviewOutcome = Literal["confirmed_fraud", "false_positive", "legitimate"]


class FraudEvaluationReviewRequest(BaseModel):
    outcome: FraudReviewOutcome
    note: str = Field(default="", max_length=1000)


class FraudEvaluationReviewOut(BaseModel):
    reviewed_by: str
    reviewed_at: datetime
    outcome: FraudReviewOutcome
    note: str = ""


class FraudEvaluationOut(BaseModel):
    id: str = Field(alias="_id")
    transaction_id: str
    user_id: str
    status: str
    score: int | None
    fired_rules: list[dict[str, Any]]
    decision_would_apply: str | None
    ruleset_version: str
    shadow_mode: bool
    evaluated_at: datetime
    error: str | None
    created_at: datetime
    review: FraudEvaluationReviewOut | None = None

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("id", "transaction_id", mode="before")
    @classmethod
    def convert_object_id(cls, value: Any) -> str:
        return str(value)


# --- Personal — rezolvare hold-uri (vezi app/holds.py, routers/staff.py) --
#
# DOAR pentru personal (RequireStaff). Distinct de FraudEvaluationOut de mai
# sus (audit/calibrare, orice evaluare) — acestea sunt DOAR reținerile încă
# nerezolvate, cu tot ce are nevoie personalul ca să decidă: scor, sumă,
# beneficiar, ȘI datele de contact ale clientului (ca să-l poată suna).


class StaffHoldCustomerContact(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone_number: str | None = None


class StaffHoldOut(BaseModel):
    id: str
    from_iban: str
    to_iban: str
    from_name: str | None = None
    to_name: str | None = None
    amount_minor: int
    currency: str
    description: str
    category: str
    status: str
    created_at: datetime
    hold_expires_at: datetime | None = None
    score: int | None = None
    fired_rule_ids: list[str] = []
    customer: StaffHoldCustomerContact | None = None


class HoldResolutionOut(BaseModel):
    id: str = Field(alias="_id")
    status: str
    resolution: str | None = None

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("id", mode="before")
    @classmethod
    def convert_object_id(cls, value: Any) -> str:
        return str(value)

    @classmethod
    def from_transaction_doc(cls, doc: dict) -> "HoldResolutionOut":
        return cls(_id=doc["_id"], status=doc["status"], resolution=(doc.get("hold") or {}).get("resolution"))
