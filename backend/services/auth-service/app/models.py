"""Modele Pydantic pentru users (auth_db).

Colecția `users` este singura folosită. Nu implementăm încă OAuth/MFA —
doar nume + email + parolă (hash bcrypt) + JWT.
"""

from datetime import datetime
from typing import Any

import email_validator
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# `email-validator` (folosit de Pydantic's EmailStr) respinge implicit
# domeniul ".local" ca fiind "special-use / reserved" (RFC 6762 — mDNS).
# MaestroBank folosește convențional adrese gen "user@maestrobank.local"
# pentru conturi demo/development — permitem explicit acest TLD, DOAR
# pentru acest motiv. Restul validărilor (format, @ prezent etc.) rămân
# neschimbate.
email_validator.SPECIAL_USE_DOMAIN_NAMES = [
    domain for domain in email_validator.SPECIAL_USE_DOMAIN_NAMES if domain != "local"
]


class UserRegister(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("first_name", "last_name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Numele nu poate fi gol.")
        return stripped

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        # Normalizare: fără spații, litere mici — ca "Test@Ex.com" și
        # "test@ex.com" să fie tratate drept ACELAȘI cont.
        return str(value).strip().lower()

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        if not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
            raise ValueError("Parola trebuie să conțină cel puțin o literă și o cifră.")
        return value


class UserLogin(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class UserOut(BaseModel):
    """Reprezentarea publică a unui user. NU conține niciodată password_hash."""

    id: str = Field(alias="_id")
    first_name: str
    last_name: str
    email: EmailStr

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("id", mode="before")
    @classmethod
    def convert_object_id(cls, value: Any) -> str:
        return str(value)


class UserMeOut(UserOut):
    """Ca UserOut, dar include și metadate — folosit pentru GET /auth/me."""

    created_at: datetime
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        if not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
            raise ValueError("Parola trebuie să conțină cel puțin o literă și o cifră.")
        return value


class InternalUserNameView(BaseModel):
    """Vedere MINIMALĂ, doar-nume, pentru alte servicii (ex. transactions-service
    afișează numele contrapărții la un transfer). NU expune email/password_hash —
    intenționat mai restrictivă decât UserOut. Rută internă, blocată la Gateway."""

    first_name: str
    last_name: str
