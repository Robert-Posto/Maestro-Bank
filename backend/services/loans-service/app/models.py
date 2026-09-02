"""DTO-uri (request/response) pentru loans-service. Formele documentelor
Mongo trăiesc informal în app/service.py (fără schema Pydantic separată
pentru documente, la fel ca restul serviciilor din acest backend)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

LoanTermMonths = Literal[12, 24, 36, 60]

# "pending_review" — cerere depusă, în așteptarea deciziei personalului (NU
# mai există aprobare automată instant, vezi app/service.py::submit_loan_
# application). "rejected" — respinsă de personal, cu motiv. Banii se
# acordă STRICT la aprobare (vezi app/service.py::approve_application), nu
# la depunerea cererii.
LoanStatus = Literal["pending_review", "active", "rejected", "paid_off"]

LoanPurpose = Literal[
    "personal_needs", "home_renovation", "purchase_goods", "debt_refinancing", "education", "medical", "vacation", "other"
]
EmploymentStatus = Literal["employed_permanent", "employed_fixed_term", "self_employed", "retired", "student", "unemployed"]
EmploymentTenure = Literal["under_6_months", "6_to_12_months", "1_to_3_years", "3_to_5_years", "over_5_years"]


class LoanRateOut(BaseModel):
    term_months: LoanTermMonths
    rate_percent_annual: float


class LoanApplicationDetails(BaseModel):
    """Chestionarul de cerere credit — răspunsurile clientului, EXACT cum
    le vede și personalul la revizuire (vezi LoanApplicationStaffOut). Nu e
    verificat automat linie cu linie (venitul declarat aici e comparat cu
    cel REAL, calculat din istoric, dar doar ca semnal afișat personalului,
    nu ca respingere automată — vezi app/eligibility.py)."""

    purpose: LoanPurpose
    employment_status: EmploymentStatus
    # Numele angajatorului SAU sursa de venit (liber profesionist, pensie
    # etc.) — text liber, ca la orice formular real de credit.
    income_source: str = Field(min_length=2, max_length=140)
    employment_tenure: EmploymentTenure
    declared_monthly_income_minor: int = Field(gt=0)
    has_other_debts: bool
    # Obligatoriu DOAR dacă has_other_debts=True — validat mai jos.
    other_debts_monthly_minor: int | None = Field(default=None, ge=0)
    dependents_count: int = Field(ge=0, le=15)
    # Consimțământ explicit pentru verificarea istoricului de tranzacții —
    # o cerere reală de credit nu poate fi depusă fără el.
    consent_credit_check: bool

    @model_validator(mode="after")
    def _validate_conditional_fields(self) -> "LoanApplicationDetails":
        if not self.consent_credit_check:
            raise ValueError("consent_credit_check_required")
        if self.has_other_debts and self.other_debts_monthly_minor is None:
            raise ValueError("other_debts_amount_required")
        return self


class LoanApplyRequest(BaseModel):
    amount_minor: int = Field(gt=0)
    term_months: LoanTermMonths
    application: LoanApplicationDetails


class EligibilitySnapshotOut(BaseModel):
    """Recomandarea AUTOMATĂ, calculată o singură dată la depunerea cererii
    (pe baza istoricului real de tranzacții) — afișată personalului ca
    semnal, NU mai e o decizie fermă (vezi app/service.py). Nu se
    recalculează la aprobare — reflectă exact ce a văzut evaluatorul."""

    average_monthly_income_minor: int
    max_affordable_installment_minor: int
    existing_installments_minor: int
    recommended: bool
    reason: str | None = None


class LoanOut(BaseModel):
    id: str
    principal_minor: int
    outstanding_principal_minor: int
    term_months: LoanTermMonths
    rate_percent_annual: float
    monthly_installment_minor: int
    payments_made: int
    applied_at: datetime
    opened_at: datetime | None = None
    next_payment_due_at: datetime | None = None
    status: LoanStatus
    paid_off_at: datetime | None = None
    rejection_reason: str | None = None
    application: LoanApplicationDetails


class LoanPaymentOut(BaseModel):
    id: str
    loan_id: str
    paid_at: datetime
    amount_minor: int
    interest_portion_minor: int
    principal_portion_minor: int
    outstanding_after_minor: int


class LoanApplicantContact(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone_number: str | None = None


class LoanApplicationStaffOut(BaseModel):
    """Vedere de PERSONAL pentru o cerere — tot ce vede evaluatorul: suma
    cerută, chestionarul complet, recomandarea automată ȘI datele de
    contact ale clientului (vezi app/routers/staff.py)."""

    id: str
    user_id: str
    applicant: LoanApplicantContact | None
    principal_minor: int
    term_months: LoanTermMonths
    rate_percent_annual: float
    monthly_installment_minor: int
    applied_at: datetime
    status: LoanStatus
    application: LoanApplicationDetails
    eligibility: EligibilitySnapshotOut
    rejection_reason: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None


class LoanApplicationRejectRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
