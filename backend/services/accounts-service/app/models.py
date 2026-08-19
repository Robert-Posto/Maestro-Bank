"""Modele Pydantic pentru accounts-service (accounts_db)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

# Design-urile disponibile pentru un card nou — vezi app/service.py::create_card.
# Sursa de adevăr pentru randare (gradient/culori) rămâne în frontend
# (Cards feature); aici doar validăm că userul a ales una dintre opțiunile
# reale, nu un string arbitrar.
CardDesign = Literal["midnight", "aurora", "rose-gold", "graphite", "arctic"]
CardType = Literal["virtual", "physical"]

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
    created_at: datetime


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


class InternalTransferRequest(BaseModel):
    from_account_id: str
    to_account_id: str
    amount_minor: int = Field(gt=0)


class InternalTransferResponse(BaseModel):
    from_balance_minor: int
    to_balance_minor: int
