"""DTO-uri (request/response) pentru deposits-service. Formele documentelor
Mongo trăiesc informal în app/service.py (fără schema Pydantic separată
pentru documente, la fel ca restul serviciilor din acest backend)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

DepositCurrency = Literal["RON", "EUR", "USD", "GBP"]
DepositTermMonths = Literal[3, 6, 12, 24]
DepositStatus = Literal["active", "matured_renewed", "liquidated_early", "closed_paid_out"]


class DepositRateOut(BaseModel):
    currency: DepositCurrency
    term_months: DepositTermMonths
    rate_percent_annual: float


class DepositOpenRequest(BaseModel):
    currency: DepositCurrency
    term_months: DepositTermMonths
    amount_minor: int = Field(gt=0)
    renew_at_maturity: bool = True


class DepositOut(BaseModel):
    id: str
    currency: DepositCurrency
    principal_minor: int
    term_months: DepositTermMonths
    rate_percent_annual: float
    # Dobânda calculată la formula standard (vezi service.py::_compute_interest_minor)
    # — informativă pt UI, NU un câmp separat stocat/actualizat în DB.
    interest_minor: int
    opened_at: datetime
    matures_at: datetime
    renew_at_maturity: bool
    status: DepositStatus
    renewed_into_deposit_id: str | None = None
    renewed_from_deposit_id: str | None = None
