"""DTO-uri (request/response) pentru loans-service. Formele documentelor
Mongo trăiesc informal în app/service.py (fără schema Pydantic separată
pentru documente, la fel ca restul serviciilor din acest backend)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

LoanTermMonths = Literal[12, 24, 36, 60]
LoanStatus = Literal["active", "paid_off"]


class LoanRateOut(BaseModel):
    term_months: LoanTermMonths
    rate_percent_annual: float


class LoanApplyRequest(BaseModel):
    amount_minor: int = Field(gt=0)
    term_months: LoanTermMonths


class LoanOut(BaseModel):
    id: str
    principal_minor: int
    outstanding_principal_minor: int
    term_months: LoanTermMonths
    rate_percent_annual: float
    monthly_installment_minor: int
    payments_made: int
    opened_at: datetime
    next_payment_due_at: datetime | None = None
    status: LoanStatus
    paid_off_at: datetime | None = None


class LoanPaymentOut(BaseModel):
    id: str
    loan_id: str
    paid_at: datetime
    amount_minor: int
    interest_portion_minor: int
    principal_portion_minor: int
    outstanding_after_minor: int
