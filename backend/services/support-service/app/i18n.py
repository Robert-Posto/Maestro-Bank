"""Traduceri RO/EN pentru mesajele orientate spre utilizator (în principal
`HTTPException.detail` și notificările declanșate direct de support-service)
— citește limba din header-ul `X-Language` trimis de front-end (RO implicit,
identic cu comportamentul de dinainte de această schimbare pentru clienți
vechi/apeluri interne service-to-service care nu trimit header-ul deloc).

Design: un `ContextVar` populat de `LanguageMiddleware` la începutul fiecărui
request, NU un parametru `request: Request` pasat explicit prin fiecare
funcție din service.py — multe funcții de business sunt apelate direct din
teste, fără obiect `Request` (vezi tests/test_documents.py), iar fallback-ul
"ro" trebuie să rămână identic cu comportamentul verificat de acele teste.

Pattern identic cu auth-service/app/i18n.py — vezi acolo pentru raționamentul
complet (inclusiv despre BackgroundTasks/create_task, care nu propagă
ContextVar-ul; support-service nu folosește niciunul dintre ele momentan).
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
    "tokenInvalidOrExpired": {"ro": "Token invalid sau expirat.", "en": "Invalid or expired token."},
    "missingAuthorizationHeader": {
        "ro": "Lipsește header-ul Authorization: Bearer <token>.",
        "en": "Missing Authorization header: Bearer <token>.",
    },
    "tokenMissingSubject": {"ro": "Token invalid: lipsește subiectul.", "en": "Invalid token: missing subject."},
    "staffOnly": {"ro": "Acces permis doar personalului.", "en": "Access is restricted to staff."},
    "invalidTicketId": {"ro": "ID de tichet invalid.", "en": "Invalid ticket ID."},
    "ticketNotFound": {"ro": "Tichetul nu există.", "en": "This ticket does not exist."},
    "invalidNotificationId": {"ro": "ID de notificare invalid.", "en": "Invalid notification ID."},
    "notificationNotFound": {"ro": "Notificarea nu există.", "en": "This notification does not exist."},
    "customerSearchFailed": {
        "ro": "Nu am putut căuta clienți — serviciul de autentificare este indisponibil.",
        "en": "We could not search for customers — the authentication service is unavailable.",
    },
    "authServiceUnavailable": {
        "ro": "Serviciul de autentificare este indisponibil.",
        "en": "The authentication service is unavailable.",
    },
    "customerNotFound": {"ro": "Clientul nu există.", "en": "This customer does not exist."},
    "invalidCustomerId": {"ro": "ID de client invalid.", "en": "Invalid customer ID."},
    "invalidDocumentId": {"ro": "ID de document invalid.", "en": "Invalid document ID."},
    "documentNotFound": {"ro": "Documentul nu există.", "en": "This document does not exist."},
    "passkeyVerificationFailed": {
        "ro": "Nu am putut verifica passkey-ul — serviciul de autentificare este indisponibil.",
        "en": "We could not verify the passkey — the authentication service is unavailable.",
    },
    "documentCannotBeSigned": {
        "ro": "Documentul nu mai poate fi semnat (deja semnat sau anulat).",
        "en": "This document can no longer be signed (already signed or cancelled).",
    },
    "incorrectPassword": {"ro": "Parolă incorectă.", "en": "Incorrect password."},
    "biometricConfirmationFailed": {"ro": "Confirmarea biometrică a eșuat.", "en": "Biometric confirmation failed."},
    "documentsOnlyPendingCanBeCancelled": {
        "ro": "Doar documentele în așteptare pot fi anulate.",
        "en": "Only pending documents can be cancelled.",
    },
    "newDocumentToSign": {
        "ro": "Ai un document nou de semnat: {title}",
        "en": "You have a new document to sign: {title}",
    },
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
