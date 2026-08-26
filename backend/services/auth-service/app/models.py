"""Modele Pydantic pentru users (auth_db).

Colecția `users` este singura folosită. Nu implementăm încă OAuth/MFA —
doar nume + email + parolă (hash bcrypt) + JWT.
"""

import re
from datetime import datetime
from typing import Any, Literal

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
    # Fictiv/necesar doar pentru fluxul de personal ("sună clientul" —
    # vezi transactions-service/app/holds.py) — NU e verificat prin SMS
    # nici acum, nici în viitorul apropiat; doar format, ca un placeholder
    # plauzibil (la fel ca IBAN-urile/PAN-urile demo din acest proiect).
    phone_number: str = Field(min_length=7, max_length=20)
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

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, value: str) -> str:
        stripped = value.strip()
        if not re.fullmatch(r"\+?[0-9 ]{7,20}", stripped):
            raise ValueError("Numărul de telefon trebuie să conțină doar cifre, spații și un + opțional la început.")
        return stripped

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
    # Absent pe conturile create înainte de introducerea rolurilor -> cade
    # automat pe "customer" (același pattern ca account_type în
    # accounts-service), fără nicio migrare. NU e citit vreodată dintr-un
    # filtru Mongo nicăieri (doar de pe un document deja găsit), deci NU
    # are nevoie de backfill — spre deosebire de account_type.
    role: Literal["customer", "staff"] = "customer"
    # Absent pe conturile create înainte de introducerea acestui câmp ->
    # cade pe None, fără migrare (același motiv ca role, mai sus).
    phone_number: str | None = None
    email_verified: bool = False
    identity_verified: bool = False
    # Poză de profil — OPȚIONALĂ (la cererea userului: "daca vrei sa ti pui
    # poza de profil"), NU obligatorie. Data URI base64 (ex.
    # "data:image/jpeg;base64,..."), redimensionată/comprimată ÎN BROWSER
    # înainte de trimitere (vezi frontend/.../profile.ts) — accounts_db
    # rămâne mic, fără nevoie de storage extern (S3 etc.) într-un demo.
    # None -> topbar/profil cad pe inițiale, ca până acum.
    profile_picture: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class EmailVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        if not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
            raise ValueError("Parola trebuie să conțină cel puțin o literă și o cifră.")
        return value


class ProfilePictureUpdate(BaseModel):
    """PATCH /auth/me/profile-picture. `profile_picture` e un data URI
    base64 (ex. "data:image/jpeg;base64,..."), redimensionat/comprimat ÎN
    BROWSER înainte de trimitere (vezi frontend/.../profile.ts) — cap de
    500 KB aici e o plasă de siguranță, nu limita "normală" (o poză demo,
    redimensionată la ~200x200, ajunge la câțiva KB). `None` șterge poza
    (revine la inițiale)."""

    profile_picture: str | None = Field(default=None, max_length=500_000)

    @field_validator("profile_picture")
    @classmethod
    def validate_data_uri(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith("data:image/"):
            raise ValueError("Poza de profil trebuie trimisă ca data URI (data:image/...).")
        return value


class InternalUserNameView(BaseModel):
    """Vedere MINIMALĂ, doar-nume, pentru alte servicii (ex. transactions-service
    afișează numele contrapărții la un transfer). NU expune email/password_hash —
    intenționat mai restrictivă decât UserOut. Rută internă, blocată la Gateway."""

    first_name: str
    last_name: str


class InternalUserContactView(BaseModel):
    """Vedere DOAR pentru personal (transactions-service::routers/staff.py —
    lista de hold-uri de revizuit), NU pentru alte scopuri (ex. contrapartida
    unui transfer, care folosește InternalUserNameView, mai restrictiv).
    Separată deliberat de InternalUserNameView — restul apelanților nu ar
    trebui să primească email/telefon doar pentru că a apărut acest câmp."""

    first_name: str
    last_name: str
    email: str
    phone_number: str | None = None


class InternalPasswordVerifyRequest(BaseModel):
    """Folosit de accounts-service pentru a confirma parola userului curent
    înainte de a dezvălui datele complete ale unui card (PAN + CVV) —
    vezi routers/internal.py::verify_password. Parola circulă DOAR pe rețeaua
    internă Docker, niciodată logată."""

    user_id: str
    password: str = Field(min_length=1)


class InternalPasswordVerifyResponse(BaseModel):
    valid: bool


class InternalMarkIdentityVerifiedRequest(BaseModel):
    """Apelat DOAR de verification-service, după un match facial reușit
    între buletin și selfie (vezi verification-service/app/service.py).
    Nu circulă imagini aici — doar rezultatul (userul e deja confirmat)."""

    user_id: str
