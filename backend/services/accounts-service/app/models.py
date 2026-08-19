"""Modele Pydantic pentru accounts-service (accounts_db)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

# Design-urile disponibile pentru un card nou — vezi app/service.py::create_card.
# Sursa de adevăr pentru randare (gradient/culori) rămâne în frontend
# (Cards feature); aici doar validăm că userul a ales una dintre opțiunile
# reale, nu un string arbitrar.
CardDesign = Literal["midnight", "aurora", "rose-gold", "graphite", "arctic"]
CardType = Literal["virtual", "physical"]

# "current" e contul unic, provizionat automat la înregistrare (vezi
# service.py::provision_account) — NU poate fi creat manual, de-aia
# AccountCreateRequest de mai jos restricționează la celelalte 3 tipuri.
AccountType = Literal["current", "savings", "deposit", "student"]
CreatableAccountType = Literal["savings", "deposit", "student"]

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
    # Default "current" — conturile create ÎNAINTE de introducerea tipurilor
    # de cont nu au acest câmp în Mongo; lipsa lui cade automat pe "current",
    # fără nicio migrare de date necesară (același pattern ca la CardOut).
    account_type: AccountType = "current"
    verification_document_name: str | None = None

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("id", "user_id", mode="before")
    @classmethod
    def convert_object_id(cls, value: Any) -> str:
        return str(value)


class AccountPublicOut(BaseModel):
    """DTO expus prin GET /accounts/me, /accounts/all și GET /accounts/{id}.

    `balance` e doar pentru convenience în UI — valoarea CANONICĂ rămâne
    `balance_minor` (întreg, în bani, NU float).
    """

    id: str
    iban: str
    currency: str
    balance_minor: int
    balance: str
    status: str
    created_at: datetime
    account_type: AccountType = "current"
    # Numele fișierului încărcat la deschidere (ex. cont student) — vezi
    # AccountCreateRequest. NU stocăm conținutul documentului (fără storage
    # de fișiere real în acest demo — vezi service.py::create_additional_account),
    # doar metadata, suficientă pentru a arăta userului "ai atașat un document".
    verification_document_name: str | None = None


class AccountCreateRequest(BaseModel):
    """POST /accounts/new — deschide un cont suplimentar (economii/depozit/student).

    Un singur cont per tip, per user (vezi service.py::create_additional_account)
    — suficient pentru acest demo, evită conturi duplicate fără sens.

    Contul de student cere un document justificativ (adeverință/carnet de
    student) — DOAR numele fișierului e trimis către backend (vezi nota de
    la `verification_document_name` din AccountPublicOut); nu există o
    verificare/aprobare umană reală în acest demo, e acceptat automat, la
    fel cum reveal-ul de card e plauzibil vizual dar nu trece printr-un
    procesator real.
    """

    account_type: CreatableAccountType
    document_filename: str | None = Field(default=None, max_length=200)

    @field_validator("document_filename")
    @classmethod
    def _strip_filename(cls, value: str | None) -> str | None:
        return value.strip() if value else value

    @model_validator(mode="after")
    def _require_document_for_student(self) -> "AccountCreateRequest":
        # `field_validator` NU rulează pe valoarea implicită (None) când
        # câmpul lipsește din payload — de-aia verificarea trăiește aici,
        # la nivel de model, care rulează întotdeauna.
        if self.account_type == "student" and not self.document_filename:
            raise ValueError("Contul de student necesită un document justificativ (adeverință sau carnet de student).")
        return self


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

    # --- Card controls (Cardul meu) ---------------------------------
    # Câmpuri cu valori implicite (nu doar în DB, ci și aici, ca DTO) —
    # astfel carduri create ÎNAINTE de introducerea acestor controale tot
    # validează corect răspunsul, fără migrare de date necesară: lipsa
    # cheii în documentul Mongo cade automat pe default-ul Pydantic.
    is_frozen: bool = False
    online_payments_enabled: bool = True
    contactless_enabled: bool = True
    atm_withdrawals_enabled: bool = True
    international_payments_enabled: bool = True
    daily_limit_minor: int = 500_000  # 5.000,00 RON — limită demo implicită

    # --- Carduri multiple / personalizare (Cardul meu) ---------------
    design: str = "midnight"
    is_one_time: bool = False

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("id", "user_id", "account_id", mode="before")
    @classmethod
    def convert_object_id(cls, value: Any) -> str:
        return str(value)


class CardCreateRequest(BaseModel):
    """POST /cards — emite un card nou pentru contul userului curent.

    Cardurile fizice ("type=physical") presupun o taxă de emitere dedusă
    din cont (vezi app/service.py::_PHYSICAL_CARD_FEE_MINOR). Cardurile de
    unică folosință ("is_one_time=True") sunt, ca la Revolut, DOAR virtuale
    — nu are sens un card fizic de unică folosință.
    """

    design: CardDesign
    type: CardType = "virtual"
    is_one_time: bool = False

    @field_validator("is_one_time")
    @classmethod
    def one_time_requires_virtual(cls, value: bool, info: ValidationInfo) -> bool:
        if value and info.data.get("type") == "physical":
            raise ValueError("Un card de unică folosință poate fi doar virtual.")
        return value


class CardRevealRequest(BaseModel):
    """POST /cards/{id}/reveal — necesită parola curentă a userului (nu doar
    JWT-ul) înainte de a dezvălui PAN/CVV — acțiune sensibilă, ca la orice
    bancă reală."""

    password: str = Field(min_length=1)


class CardRevealOut(BaseModel):
    pan: str
    cvv: str
    expiry_month: int
    expiry_year: int


class CardSettingsUpdate(BaseModel):
    """PATCH /cards/{id}/settings — doar câmpurile trimise sunt actualizate."""

    online_payments_enabled: bool | None = None
    contactless_enabled: bool | None = None
    atm_withdrawals_enabled: bool | None = None
    international_payments_enabled: bool | None = None


class CardLimitUpdate(BaseModel):
    daily_limit_minor: int = Field(gt=0, le=100_000_000)  # cap defensiv: max 1.000.000,00 RON/zi


# --- Beneficiari (transfer către IBAN salvat) -----------------------------


class BeneficiaryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=140)
    iban: str = Field(min_length=10, max_length=34)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Numele beneficiarului nu poate fi gol.")
        return stripped

    @field_validator("iban")
    @classmethod
    def normalize_iban(cls, value: str) -> str:
        return value.strip().upper().replace(" ", "")


class BeneficiaryOut(BaseModel):
    id: str = Field(alias="_id")
    name: str
    iban: str
    created_at: datetime

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("id", mode="before")
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
    account_type: AccountType = "current"


class InternalTransferRequest(BaseModel):
    from_account_id: str
    to_account_id: str
    amount_minor: int = Field(gt=0)


class InternalTransferResponse(BaseModel):
    from_balance_minor: int
    to_balance_minor: int
