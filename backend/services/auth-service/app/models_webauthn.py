"""Modele Pydantic pentru WebAuthn / passkeys (auth_db.webauthn_credentials,
auth_db.webauthn_challenges).

Separat de models.py (users/parole) — suprafață conceptual distinctă.
Logica de business trăiește în app/webauthn_service.py, aici doar DTO-uri.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class WebauthnOptionsOut(BaseModel):
    """Răspuns comun pentru toate rutele *.../options — `challenge_id`
    identifică challenge-ul stocat server-side (Mongo, single-use + TTL),
    `options` e JSON-ul gata de trimis către @simplewebauthn/browser
    (startRegistration / startAuthentication)."""

    challenge_id: str
    options: dict[str, Any]


class WebauthnRegisterVerifyRequest(BaseModel):
    challenge_id: str = Field(min_length=1)
    credential: dict[str, Any]


class WebauthnLoginOptionsRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class WebauthnLoginVerifyRequest(BaseModel):
    challenge_id: str = Field(min_length=1)
    credential: dict[str, Any]


class WebauthnStepUpOptionsRequest(BaseModel):
    """Cerut de frontend (prin Gateway, JWT-protejat) pentru a începe un
    step-up legat de o acțiune specifică — vezi
    app/webauthn_service.py::begin_step_up. `action_payload` e stocat în
    challenge și verificat din nou la finalizare (accounts-service trimite
    valoarea rezolvată server-side, ex. card_id, niciodată una trimisă de
    client) — un assertion capturat pentru o acțiune nu poate fi refolosit
    pentru alta."""

    action: str = Field(min_length=1, max_length=60)
    action_payload: str = Field(min_length=1, max_length=200)


class CredentialOut(BaseModel):
    """NU expune niciodată `public_key` — cheia publică rămâne strict
    server-side, nu are ce căuta în răspunsul către client."""

    id: str = Field(alias="_id")
    created_at: datetime
    last_used_at: datetime | None = None

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("id", mode="before")
    @classmethod
    def convert_object_id(cls, value: Any) -> str:
        return str(value)


# --- Rute INTERNE (service-to-service, ex. accounts-service la reveal card) -


class InternalWebauthnVerifyRequest(BaseModel):
    user_id: str
    challenge_id: str
    action: str
    action_payload: str
    credential: dict[str, Any]


class InternalWebauthnVerifyResponse(BaseModel):
    valid: bool
