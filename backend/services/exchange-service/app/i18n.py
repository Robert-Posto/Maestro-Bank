"""Traduceri RO/EN pentru mesajele orientate spre utilizator (în principal
`HTTPException.detail`) — citește limba din header-ul `X-Language` trimis de
front-end (RO implicit, identic cu comportamentul de dinainte de această
schimbare pentru clienți vechi/apeluri interne service-to-service care nu
trimit header-ul deloc).

Design: un `ContextVar` populat de `LanguageMiddleware` la începutul fiecărui
request, NU un parametru `request: Request` pasat explicit prin fiecare
funcție din service.py — multe funcții de business sunt apelate direct din
teste, fără obiect `Request` (vezi tests/test_exchange.py), iar fallback-ul
"ro" trebuie să rămână identic cu comportamentul verificat de acele teste.

Vezi auth-service/app/i18n.py pentru implementarea de referință — acest
modul e o copie independentă a aceluiași pattern (fiecare serviciu are
propriul ContextVar, propriul dict T), NU un import comun.
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
    # Identice cu auth-service — aceleași chei/text, folosite ca convenție
    # de stil (fiecare serviciu validează JWT-ul independent, defense in
    # depth, vezi app/security.py), nu ca o dependență tehnică comună.
    "missingAuthorizationHeader": {
        "ro": "Lipsește header-ul Authorization: Bearer <token>.",
        "en": "Missing Authorization header: Bearer <token>.",
    },
    "tokenInvalidOrExpired": {"ro": "Token invalid sau expirat.", "en": "Invalid or expired token."},
    "tokenMissingSubject": {"ro": "Token invalid: lipsește subiectul.", "en": "Invalid token: missing subject."},
    "unsupportedCurrencyPair": {
        "ro": "Pereche valutară nesuportată. Perechi disponibile: RON <-> {currencies}.",
        "en": "Unsupported currency pair. Available pairs: RON <-> {currencies}.",
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
