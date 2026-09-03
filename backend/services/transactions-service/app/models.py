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
    # PIN-ul cardului — necesar DOAR dacă transferul depășește pragul de
    # "Payment confirmation" (Security settings, Cardul meu) ȘI contul
    # sursă are acest control activat pe vreun card — vezi
    # service.py::_PAYMENT_CONFIRMATION_THRESHOLD_MINOR. Frontend-ul
    # retrimite EXACT același request, cu acest câmp completat, după ce
    # backend-ul respinge prima încercare cu 428 (vezi create_transfer).
    card_pin: str | None = Field(default=None, min_length=4, max_length=4)

    @field_validator("to_iban")
    @classmethod
    def normalize_iban(cls, value: str) -> str:
        return value.strip().upper().replace(" ", "")

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        normalized = (value or "other").strip().lower()
        return normalized if normalized in TRANSACTION_CATEGORIES else "other"


# Reîncărcare telefon (diaspora) — vezi service.py::create_topup. NU e un
# tip nou de tranzacție: devine un TransferRequest normal, către contul-
# pseudo al operatorului (accounts-service), cu tot ce implică asta (motor
# de fraudă, content screening) — vezi service.py pentru raționament.
TOPUP_OPERATORS: list[str] = ["orange", "vodafone", "digi", "telekom"]


class TopupRequest(BaseModel):
    """Input primit de la Angular pentru POST /transactions/topups."""

    operator: Literal["orange", "vodafone", "digi", "telekom"]
    # Format RO simplu — 07xxxxxxxx (10 cifre) — suficient pentru un demo,
    # NU o validare completă de numerotare telefonică reală.
    phone_number: str = Field(min_length=10, max_length=10)
    amount_minor: int = Field(gt=0, le=100_000)  # cap 1.000,00 RON/reîncărcare — o reîncărcare, nu un transfer mare
    # Prima încercare (din frontend) NU o are — dacă Twilio Lookup detectează
    # că numărul aparține altui operator decât cel selectat, backend-ul
    # respinge cu 428 ÎNAINTE de a mișca banii (vezi service.py::
    # create_topup), frontend-ul arată un dialog de confirmare și
    # RETRIMITE exact același request, cu acest câmp pe True — mirror exact
    # pe `card_pin`/428 de la TransferRequest, mai sus.
    confirm_mismatch: bool = Field(default=False)

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped.isdigit() or not stripped.startswith("07"):
            raise ValueError("Numărul de telefon trebuie să fie în format 07xxxxxxxx (10 cifre).")
        return stripped


class DescriptionCheckRequest(BaseModel):
    """POST /transactions/transfers/screen-description — verificare LIVE,
    în timp ce userul scrie în câmpul de descriere (înainte de a trimite
    efectiv transferul), vezi app/content_screening.py. Fără efecte
    secundare — nu creează nimic, doar rulează același screening
    determinist ca la crearea reală a transferului."""

    description: str = Field(default="", max_length=140)


class DescriptionCheckResponse(BaseModel):
    warning: str | None = None


class HoldInfoOut(BaseModel):
    """Prezent DOAR pe o tranzacție reținută (status="pending_review" sau
    care A FOST reținută) — vezi app/holds.py."""

    expires_at: datetime
    resolution: str | None = None


class RiskOut(BaseModel):
    """Nivelul de risc AFIȘABIL CLIENTULUI — vezi app/guardian/service.py.
    `tier`/`status` sunt calculate SINCRON, fără LLM; `phrase` pentru
    "unusual"/"potentially_dangerous" e completată ASINCRON (status trece
    din "pending" în "ready"/"template_fallback"). NU conține NICIODATĂ
    ID-uri de regulă sau alte detalii care ar putea fi folosite ca să
    "învețe" pragurile motorului — vezi guardian/prompt.py."""

    tier: Literal["safe", "unusual", "potentially_dangerous", "held"]
    phrase: str | None = None
    status: Literal["pending", "ready", "template_fallback"]


class PhoneVerificationOut(BaseModel):
    """Rezultatul verificării REALE (Twilio Lookup) a numărului de telefon la
    o reîncărcare — vezi service.py::_verify_topup_phone /
    app/twilio_client.py. Prezent DOAR pe tranzacții create prin
    create_topup; None pentru orice altă tranzacție (transfer normal etc.).

    `checked=False` distinge explicit DE CE n-a fost verificat
    (`unavailable_reason`) — userul trebuie să vadă mereu dacă verificarea
    chiar a avut loc, nu doar o tăcere identică unui succes."""

    checked: bool
    carrier_name: str | None = None
    line_type: str | None = None
    # None = neconcludent (Twilio n-a întors un nume de operator recunoscut),
    # NU o nepotrivire — vezi service.py::_carrier_matches_operator.
    operator_match: bool | None = None
    unavailable_reason: Literal["not_configured", "request_failed"] | None = None


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
    risk: RiskOut | None = None
    # Screening determinist al descrierii (termeni de terorism/violență —
    # vezi app/content_screening.py), NEcondiționat de motorul de fraudă
    # (app/fraud/) — un semnal complet separat. Informativ, NU blochează
    # transferul (vezi service.py::create_transfer).
    content_warning: str | None = None
    # Prezent DOAR pe reîncărcări de telefon (vezi PhoneVerificationOut) —
    # None pentru orice altă tranzacție.
    phone_verification: PhoneVerificationOut | None = None

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


# --- Cereri de plată (link/QR de tip "Request Money", ca la Revolut) ------
#
# Userul A generează o cerere cu o SUMĂ FIXĂ (stabilită de A, la creare —
# la fel ca la Revolut, nu userul B alege cât plătește). Link-ul rezultat
# (frontend: /app/pay/{id}) poate fi trimis oricui — dar vizualizarea ȘI
# plata cer login în MaestroBank (nu există procesare de plăți externe în
# acest demo — vezi task-ul, "no real Visa/Mastercard/SEPA/PSD2/FX
# integration"), ca să NU fie nevoie să facem PUBLICĂ nicio rută nouă în
# Gateway (toate rutele /api/transactions/* rămân protejate uniform, la
# fel ca până acum — vezi backend/gateway/app/routers/proxy.py).
#
# Plata efectivă REFOLOSEȘTE create_transfer (exact aceeași validare,
# screening de conținut, motor de fraudă, Guardian — vezi
# app/service.py::pay_payment_request), nu duplică nimic.
#
# Screening-ul de conținut (app/content_screening.py) e mai STRICT aici
# decât la un transfer normal — la un transfer (deja finalizat, între doi
# useri autentificați) doar AVERTIZĂM (vezi content_warning din
# TransactionOut). O cerere de plată e altceva: un link/cod QR generat ca
# să fie trimis mai departe, către oricine — un "anunț public" de facto,
# nu o tranzacție privată deja consumată. De-aia BLOCĂM crearea (vezi
# app/service.py::create_payment_request) dacă descrierea conține termeni
# marcați, în loc doar să avertizăm — nu există niciodată o cerere de
# plată creată cu conținut marcat, deci PaymentRequestOut nu mai are
# nevoie de un câmp content_warning (spre deosebire de TransactionOut).

PaymentRequestStatus = Literal["open", "paid", "cancelled", "expired"]


class PaymentRequestCreate(BaseModel):
    amount_minor: int = Field(gt=0, le=100_000_000)
    description: str = Field(default="", max_length=140)


class PaymentRequestOut(BaseModel):
    id: str = Field(alias="_id")
    requester_name: str | None = None
    requester_iban: str
    amount_minor: int
    currency: str
    description: str
    status: PaymentRequestStatus
    created_at: datetime
    expires_at: datetime
    paid_at: datetime | None = None
    paid_by_name: str | None = None

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


class GuardianOut(BaseModel):
    """Output-ul Guardian (app/guardian/) pentru o evaluare — vezi
    app/guardian/service.py::generate_guardian_explanations. `staff_
    explanation` NU trebuie NICIODATĂ expus printr-un DTO orientat spre
    client (vezi TransactionOut, care nu-l conține deloc)."""

    status: Literal["ready", "template_fallback"]
    staff_explanation: str | None = None
    customer_tier: str | None = None
    customer_phrase: str | None = None
    source: Literal["llm", "template"] | None = None
    generated_at: datetime | None = None
    model: str | None = None


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
    guardian: GuardianOut | None = None

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
    user_id: str | None = None
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
    guardian_staff_explanation: str | None = None
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


# --- Personal — blocklist de beneficiari (vezi app/blocklist.py, BEN-04) ---
#
# Scriere DOAR de personal — niciodată dintr-un raport de fraudă al unui
# client (vezi motivul în docstring-ul app/blocklist.py).


class BlocklistCreateRequest(BaseModel):
    iban: str = Field(min_length=10, max_length=34)
    reason: str = Field(default="", max_length=280)

    @field_validator("iban")
    @classmethod
    def normalize_iban(cls, value: str) -> str:
        return value.strip().upper().replace(" ", "")


class BlocklistEntryOut(BaseModel):
    id: str = Field(alias="_id")
    iban: str
    added_by: str
    reason: str
    source: Literal["confirmed_fraud_review", "manual"]
    evaluation_id: str | None = None
    created_at: datetime

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("id", "evaluation_id", mode="before")
    @classmethod
    def convert_object_id(cls, value: Any) -> str | None:
        return str(value) if value is not None else None
