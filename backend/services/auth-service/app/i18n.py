"""Traduceri RO/EN pentru mesajele orientate spre utilizator (în principal
`HTTPException.detail`) — citește limba din header-ul `X-Language` trimis de
front-end (RO implicit, identic cu comportamentul de dinainte de această
schimbare pentru clienți vechi/apeluri interne service-to-service care nu
trimit header-ul deloc).

Design: un `ContextVar` populat de `LanguageMiddleware` la începutul fiecărui
request, NU un parametru `request: Request` pasat explicit prin fiecare
funcție din service.py — multe funcții de business sunt apelate direct din
teste, fără obiect `Request` (vezi tests/test_auth.py), iar fallback-ul "ro"
trebuie să rămână identic cu comportamentul verificat de acele teste.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Literal

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

Language = Literal["ro", "en"]

_current_language: ContextVar[Language] = ContextVar("_current_language", default="ro")


class LanguageMiddleware(BaseHTTPMiddleware):
    """Citește `X-Language` (ro|en, implicit ro) și îl expune prin ContextVar
    pentru toată durata request-ului — vezi `translate()` mai jos."""

    async def dispatch(self, request: Request, call_next) -> Response:
        raw = (request.headers.get("x-language") or "ro").lower()
        token = _current_language.set(raw if raw in ("ro", "en") else "ro")
        try:
            return await call_next(request)
        finally:
            _current_language.reset(token)


T: dict[str, dict[Language, str]] = {
    "userExists": {"ro": "Există deja un cont cu acest email.", "en": "An account with this email already exists."},
    "userNotFound": {"ro": "Utilizatorul nu există.", "en": "This user does not exist."},
    "userNoLongerExists": {"ro": "Utilizatorul nu mai există.", "en": "This user no longer exists."},
    "requestVerificationCodeFirst": {
        "ro": "Cere mai întâi un cod de verificare.",
        "en": "Request a verification code first.",
    },
    "codeExpired": {"ro": "Codul a expirat. Cere unul nou.", "en": "The code has expired. Request a new one."},
    "incorrectCode": {"ro": "Cod incorect.", "en": "Incorrect code."},
    "invalidUserId": {"ro": "ID de utilizator invalid.", "en": "Invalid user ID."},
    "invalidCredentials": {"ro": "Email sau parolă incorectă.", "en": "Incorrect email or password."},
    "accountDisabled": {"ro": "Contul este dezactivat.", "en": "This account is disabled."},
    "missingAuthorizationHeader": {
        "ro": "Lipsește header-ul Authorization: Bearer <token>.",
        "en": "Missing Authorization header: Bearer <token>.",
    },
    "tokenInvalidOrExpired": {"ro": "Token invalid sau expirat.", "en": "Invalid or expired token."},
    "tokenInvalid": {"ro": "Token invalid.", "en": "Invalid token."},
    "tokenMissingSubject": {"ro": "Token invalid: lipsește subiectul.", "en": "Invalid token: missing subject."},
    "currentPasswordIncorrect": {"ro": "Parola curentă este incorectă.", "en": "The current password is incorrect."},
    "challengeInvalid": {"ro": "Challenge invalid.", "en": "Invalid challenge."},
    "challengeInvalidOrUsed": {
        "ro": "Challenge invalid sau deja folosit.",
        "en": "Invalid challenge, or it was already used.",
    },
    "challengeExpired": {"ro": "Challenge expirat.", "en": "The challenge has expired."},
    "passkeyRevokedCompromised": {
        "ro": "Acest passkey pare compromis și a fost revocat automat. Adaugă unul nou.",
        "en": "This passkey appears to be compromised and was automatically revoked. Add a new one.",
    },
    "maxPasskeysReached": {
        "ro": "Ai atins numărul maxim de passkey-uri ({max_credentials}).",
        "en": "You've reached the maximum number of passkeys ({max_credentials}).",
    },
    "passkeyRegistrationFailed": {
        "ro": "Nu am putut înregistra passkey-ul.",
        "en": "We could not register the passkey.",
    },
    "passkeyAlreadyRegistered": {
        "ro": "Acest passkey este deja înregistrat.",
        "en": "This passkey is already registered.",
    },
    "noPasskeyForEmail": {
        "ro": "Nu există niciun passkey înregistrat pentru acest email.",
        "en": "There is no passkey registered for this email.",
    },
    "noPasskeyRegistered": {"ro": "Nu ai niciun passkey înregistrat.", "en": "You don't have any passkey registered."},
    "invalidPasskeyId": {"ro": "ID de passkey invalid.", "en": "Invalid passkey ID."},
    "passkeyNotFound": {"ro": "Passkey-ul nu există.", "en": "This passkey does not exist."},
}


def current_language() -> Language:
    """Limba cerută de request-ul curent — de folosit când textul tradus
    trebuie compus ÎNAINTE de a fi pasat unui `BackgroundTasks.add_task`/
    `asyncio.create_task` (ContextVar-ul NU se propagă fiabil într-un task
    programat pentru DUPĂ ce răspunsul a fost trimis; captează limba
    sincron, în timpul request-ului, nu în interiorul task-ului însuși)."""
    return _current_language.get()


def translate(key: str, **params: object) -> str:
    entry = T.get(key)
    if entry is None:
        return key
    language = _current_language.get()
    text = entry.get(language) or entry.get("ro") or key
    if params:
        text = text.format(**params)
    return text
