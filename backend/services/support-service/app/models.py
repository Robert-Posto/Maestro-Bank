"""Modele Pydantic pentru support-service (support_db, colecțiile `tickets`,
`notifications`, `documents`)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TICKET_CATEGORIES: list[str] = ["card", "transfer", "account", "technical", "other"]
TICKET_STATUSES: list[str] = ["open", "in_progress", "resolved"]


class TicketCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=140)
    category: Literal["card", "transfer", "account", "technical", "other"] = "other"
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("subject", "message")
    @classmethod
    def strip_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Câmpul nu poate fi gol.")
        return stripped


class TicketOut(BaseModel):
    id: str = Field(alias="_id")
    subject: str
    category: str
    message: str
    status: str = "open"
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("id", mode="before")
    @classmethod
    def convert_object_id(cls, value: Any) -> str:
        return str(value)


# --- Notificări (istoric persistent, alimentat de alte servicii) ---------
#
# Vezi app/routers/notifications.py — POST /internal/notifications e apelat
# de accounts-service (card blocat), budgets-service (prag de buget atins),
# transactions-service (transfer reușit), NU direct de frontend.

NotificationKind = Literal[
    "budget", "card", "transfer", "transfer_received", "transfer_hold", "transfer_hold_cancelled", "system",
    "document_sign", "reward_redeemed", "raffle_win",
    "loan_approved", "loan_payment", "loan_payment_missed", "loan_paid_off",
]


class NotificationCreate(BaseModel):
    """Payload-ul trimis de UN ALT serviciu, prin POST /internal/notifications."""

    user_id: str
    kind: NotificationKind
    text: str = Field(min_length=1, max_length=280)
    # Id-ul resursei la care se referă notificarea (ex. id-ul tranzacției
    # pentru un transfer) — opțional, doar serviciile care au un id relevant
    # îl trimit. Folosit de frontend ca să deschidă direct acea resursă la
    # click, nu doar pagina ei generică (vezi Topbar::openNotification).
    reference_id: str | None = None


class NotificationOut(BaseModel):
    id: str = Field(alias="_id")
    kind: str
    text: str
    read: bool
    created_at: datetime
    reference_id: str | None = None

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("id", mode="before")
    @classmethod
    def convert_object_id(cls, value: Any) -> str:
        return str(value)


# --- Documente de semnat (eSign) ---------------------------------------
#
# Personalul trimite un PDF unui client oarecare (căutat prin auth-service —
# vezi service.py::search_customers); clientul îl vede/semnează din Profil,
# cu un click de confirmare protejat prin step-up (parolă SAU passkey, la
# fel ca reveal-ul de card din accounts-service). Fără storage extern — PDF-ul
# e stocat direct ca data-URI base64 în Mongo, la fel ca ProfilePictureUpdate
# din auth-service (singurul precedent din acest stack).

DocumentStatus = Literal["pending", "signed", "cancelled"]

_PDF_DATA_URI_PREFIX = "data:application/pdf;base64,"


class DocumentCreate(BaseModel):
    """Trimis DOAR de personal — POST /staff/documents. Limita de
    max_length (~5MB PDF brut, encodat) ține documentul sub limita BSON de
    16MB per document Mongo, cu marjă confortabilă."""

    user_id: str
    title: str = Field(min_length=1, max_length=140)
    pdf_data: str = Field(max_length=7_000_000)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Titlul nu poate fi gol.")
        return stripped

    @field_validator("pdf_data")
    @classmethod
    def validate_pdf_data_uri(cls, value: str) -> str:
        if not value.startswith(_PDF_DATA_URI_PREFIX):
            raise ValueError("Documentul trebuie să fie un PDF valid (data URI application/pdf).")
        return value


class DocumentSummaryOut(BaseModel):
    """Pentru liste — FĂRĂ `pdf_data` (poate fi mare, inutil de trimis pentru
    fiecare rând al unei liste)."""

    id: str = Field(alias="_id")
    title: str
    status: DocumentStatus
    created_at: datetime
    signed_at: datetime | None = None

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("id", mode="before")
    @classmethod
    def convert_object_id(cls, value: Any) -> str:
        return str(value)


class DocumentOut(DocumentSummaryOut):
    """Un singur document, de vizualizat/semnat — include `pdf_data`."""

    pdf_data: str


class StaffDocumentOut(DocumentSummaryOut):
    """Vedere de personal — include numele clientului, stocat direct pe
    document la creare (vezi service.py::create_document), ca listarea să nu
    facă un apel HTTP suplimentar per rând."""

    user_id: str
    customer_name: str


class DocumentSignRequest(BaseModel):
    """La fel ca CardRevealRequest din accounts-service — exact UNA dintre
    parolă sau confirmare WebAuthn (step-up), nu ambele/niciuna."""

    password: str | None = None
    webauthn_challenge_id: str | None = None
    webauthn_assertion: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _exactly_one_method(self) -> "DocumentSignRequest":
        has_password = self.password is not None
        has_webauthn = self.webauthn_challenge_id is not None and self.webauthn_assertion is not None
        if has_password == has_webauthn:
            raise ValueError("Trimite fie parola, fie o confirmare biometrică — nu ambele sau niciuna.")
        return self


class StaffCustomerSearchResult(BaseModel):
    """Mirror pe InternalUserSearchResult din auth-service — vedere de
    personal pentru căutarea unui client la trimiterea unui document."""

    id: str
    first_name: str
    last_name: str
    email: str
