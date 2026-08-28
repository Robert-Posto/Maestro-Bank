"""Limba RO/EN pentru textul orientat spre utilizator generat de acest
serviciu — răspunsuri deterministe (filtre de moderare/siguranță, fallback-uri),
câmpul `recommendation`, întrebările de confirmare, `HTTPException.detail` — ȘI
directiva de limbă injectată în system prompt-ul celor doi agenți, ca modelul
să răspundă în limba din UI, nu în cea ghicită din mesaj.

Citește `X-Language` (trimis de front-end pe fiecare request — vezi
frontend/src/app/core/language.interceptor.ts) printr-un `ContextVar` populat
de `LanguageMiddleware`, NU un parametru pasat prin fiecare funcție: multe
funcții deterministe sunt apelate direct din teste, fără obiect `Request`
(vezi tests/test_affordability_service.py), iar fallback-ul "ro" trebuie să
rămână identic cu comportamentul verificat de acele teste.

Vezi transactions-service/app/i18n.py pentru implementarea de referință —
acest modul e o copie independentă a aceluiași pattern (fiecare serviciu are
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
    pentru toată durata request-ului — vezi `translate()` / `current_language()`."""

    async def dispatch(self, request: Request, call_next) -> Response:
        raw = (request.headers.get("x-language") or "ro").lower()
        token = _current_language.set(raw if raw in ("ro", "en") else "ro")
        try:
            return await call_next(request)
        finally:
            _current_language.reset(token)


def current_language() -> Language:
    """Limba cerută de request-ul curent (implicit "ro" în afara unui
    request — ex. apel direct dintr-un test)."""
    return _current_language.get()


def pick(ro: str, en: str) -> str:
    """Alege varianta pentru limba curentă — pentru textele lungi, asamblate
    condiționat (ex. `render_recommendation`), unde un `T[key]` cu `.format`
    ar fi mai greu de citit decât două șabloane alăturate."""
    return en if _current_language.get() == "en" else ro


T: dict[str, dict[Language, str]] = {
    # --- security.py (JWT) ------------------------------------------------
    "tokenInvalidOrExpired": {"ro": "Token invalid sau expirat.", "en": "Invalid or expired token."},
    "missingAuthorizationHeader": {
        "ro": "Lipsește header-ul Authorization: Bearer <token>.",
        "en": "Missing Authorization header: Bearer <token>.",
    },
    "tokenMissingSubject": {"ro": "Token invalid: lipsește subiectul.", "en": "Invalid token: missing subject."},
    # --- conversation_service.py (istoric conversații) --------------------
    "invalidConversationId": {"ro": "ID de conversație invalid.", "en": "Invalid conversation ID."},
    "conversationNotFound": {"ro": "Conversația nu există.", "en": "This conversation does not exist."},
    # --- agenți: erori Azure OpenAI (HTTPException.detail) --------------
    "assistantNotConfigured": {
        "ro": "Asistentul AI nu este configurat momentan.",
        "en": "The AI assistant is not configured right now.",
    },
    "assistantUnreachable": {
        "ro": "Nu am putut contacta asistentul AI. Te rugăm să încerci din nou.",
        "en": "We couldn't reach the AI assistant. Please try again.",
    },
    "azureError": {
        "ro": "Azure OpenAI a răspuns cu eroare ({error_type}). Verifică endpoint/deployment/cheia din .env.",
        "en": "Azure OpenAI returned an error ({error_type}). Check the endpoint/deployment/key in .env.",
    },
    "speechSynthesisFailed": {
        "ro": "Sinteza vocală a eșuat momentan.",
        "en": "Speech synthesis failed for now.",
    },
    # --- Spending + Forecast Agent: fallback ----------------------------
    "forecastFallbackAnswer": {
        "ro": "Nu am putut genera o explicație completă acum, dar mai jos ai situația ta financiară curentă.",
        "en": "I couldn't produce a full explanation right now, but your current financial situation is shown below.",
    },
    # --- Support Agent: fallback ---------------------------------------
    "supportFallbackAnswer": {
        "ro": "Nu am putut finaliza răspunsul — poți reformula întrebarea, te rog?",
        "en": "I couldn't finish the answer — could you rephrase your question, please?",
    },
    "unknownAction": {"ro": "Acțiune necunoscută.", "en": "Unknown action."},
    # --- moderation_service.py --------------------------------------------
    "rephraseRequest": {
        "ro": "Hai să păstrăm un ton respectuos, ca să te pot ajuta eficient — poți reformula, te rog?",
        "en": "Let's keep a respectful tone so I can help you properly — could you rephrase, please?",
    },
    # --- safety_guard.py -----------------------------------------------
    "sensitiveDataWarning": {
        "ro": (
            "Nu introduce niciodată PIN-ul, CVV-ul sau numărul complet al cardului într-o conversație — "
            'nici cu mine, nici cu altcineva. Pentru aceste date, mergi la "Cardul meu" din aplicație, '
            "unde sunt protejate prin verificare suplimentară (PIN-ul cardului sau passkey)."
        ),
        "en": (
            "Never enter your PIN, CVV or full card number in a conversation — not with me, not with anyone. "
            'For those details, go to "My card" in the app, where they are protected by an extra check '
            "(card PIN or passkey)."
        ),
    },
    "promptExtractionRefusal": {
        "ro": (
            "Nu pot să-ți arăt instrucțiunile mele interne — dar te pot ajuta cu întrebări reale despre "
            "cont, card, tranzacții sau finanțele tale."
        ),
        "en": (
            "I can't show you my internal instructions — but I can help with real questions about your "
            "account, card, transactions or finances."
        ),
    },
    # --- support_service.py: confirmare / rezultat tichet -------------
    "confirmCreateTicket": {
        "ro": 'Vrei să creez o solicitare de suport cu subiectul "{subject}" (categorie: {category})? Confirmă cu "da".',
        "en": 'Do you want me to open a support request titled "{subject}" (category: {category})? Confirm with "yes".',
    },
    "confirmGenericAction": {"ro": "Confirmi această acțiune?", "en": "Do you confirm this action?"},
    "ticketCreateFailed": {
        "ro": "Nu am putut crea solicitarea: {error}",
        "en": "I couldn't create the request: {error}",
    },
    "ticketCreated": {
        "ro": "Solicitarea a fost creată cu numărul {id}. Status: {status}.",
        "en": "The request was created with number {id}. Status: {status}.",
    },
    "viewMyTickets": {"ro": "Vezi solicitările mele", "en": "View my requests"},
}


def translate(key: str, **params: object) -> str:
    entry = T.get(key)
    if entry is None:
        return key
    language = _current_language.get()
    text = entry.get(language) or entry.get("ro") or key
    if params:
        text = text.format(**params)
    return text
