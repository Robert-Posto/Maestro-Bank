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

import re
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
}


# --- Notificări: catalog RENDERED-AT-READ ---------------------------------
#
# Notificările NU se mai stochează ca text gata-format — serviciile-sursă
# (accounts/loans/transactions + support-service însuși) trimit doar
# `message_key` + `message_params` (valori BRUTE: `*_minor`, `currency`,
# nume, numere). `render_notification()` de mai jos le compune în limba
# CITITORULUI, la fiecare `GET /notifications` — deci o notificare veche își
# schimbă limba când userul comută comutatorul, retroactiv.
#
# Placeholder-ele de bani (`{amount}`, `{instalment}`, `{income}`,
# `{available}`) vin din parametri `*_minor` + `currency` (implicit "RON"),
# formatate de `_fmt_money` — sursa NU mai formatează nimic.
NOTIFICATION_MESSAGES: dict[str, dict[Language, str]] = {
    # support-service (documente de semnat)
    "newDocumentToSign": {
        "ro": "Ai un document nou de semnat: {title}",
        "en": "You have a new document to sign: {title}",
    },
    # accounts-service
    "cardBlocked": {
        "ro": "Cardul terminat în {last_four} a fost blocat.",
        "en": "The card ending in {last_four} has been blocked.",
    },
    # transactions-service
    "transferHold": {
        "ro": "Transferul de {amount} către {iban} este în verificare de securitate — vei fi anunțat imediat ce e rezolvat.",
        "en": "Your transfer of {amount} to {iban} is under security review — you'll be notified as soon as it's resolved.",
    },
    "transferSuccess": {
        "ro": "Transfer de {amount} către {iban} — reușit.",
        "en": "Transfer of {amount} to {iban} — successful.",
    },
    "transferReceived": {
        "ro": "Ai primit {amount} de la {name}.",
        "en": "You received {amount} from {name}.",
    },
    "transferHoldCancelled": {
        "ro": "Ai anulat transferul reținut — fondurile au revenit în cont.",
        "en": "You cancelled the held transfer — the funds have returned to your account.",
    },
    # loans-service
    "loanApproved": {
        "ro": "Creditul tău de {amount} a fost aprobat — rata lunară e {instalment}, pe {months} luni.",
        "en": "Your loan of {amount} was approved — the monthly instalment is {instalment}, over {months} months.",
    },
    "loanPaidOffEarly": {
        "ro": "Ai plătit anticipat restul de {amount} — creditul e închis.",
        "en": "You paid off the remaining {amount} early — the loan is closed.",
    },
    "loanPaymentMissed": {
        "ro": "Rata de {amount} nu a putut fi plătită — sold insuficient. Reîncercăm automat.",
        "en": "The {amount} instalment could not be paid — insufficient balance. We'll retry automatically.",
    },
    "loanPayment": {
        "ro": "Rata de {amount} a fost plătită automat.",
        "en": "The {amount} instalment was paid automatically.",
    },
    "loanClosed": {
        "ro": "Ultima rată a fost plătită — creditul e închis.",
        "en": "The final instalment was paid — the loan is closed.",
    },
}


def _fmt_money(amount_minor: int, currency: str, language: Language) -> str:
    """"880,00 lei" (ro, RON) / "880.00 RON" (en) / "50,00 EUR" (ro, valută).
    RO folosește "lei" pentru RON ca să fie consecvent cu paginile din UI;
    engleza folosește codul ISO peste tot."""
    sign = "-" if amount_minor < 0 else ""
    major, minor = divmod(abs(int(amount_minor)), 100)
    if language == "en":
        return f"{sign}{major}.{minor:02d} {currency}"
    label = "lei" if currency.upper() == "RON" else currency
    return f"{sign}{major},{minor:02d} {label}"


# Placeholder-e care conțin bani (formatate de `_fmt_money`) vs. text simplu.
_MONEY_PLACEHOLDERS = {"amount", "instalment", "income", "available"}
_TITLE_PLACEHOLDERS = {"title"}

_MONEY_RE = re.compile(r"^(-?)(\d+)[.,](\d{2})\s*(lei|RON|EUR|USD|GBP)$", re.IGNORECASE)
_PLACEHOLDER_RE = re.compile(r"\{([a-z_]+)\}")


def _parse_money(text: str) -> tuple[int, str] | None:
    """"2500.00 RON" / "10000,00 lei" / "100,00 EUR" -> (minor, currency).
    Acoperă ambele formate istorice (transactions: `X.XX RON`; loans/points:
    `X.XX lei`) și pe cel nou (`X,XX lei`). Fără separator de mii în niciunul."""
    m = _MONEY_RE.match(text.strip())
    if not m:
        return None
    sign, major, cents, cur = m.groups()
    minor = (int(major) * 100 + int(cents)) * (-1 if sign else 1)
    return minor, ("RON" if cur.lower() == "lei" else cur.upper())


def _lei_to_ron(text: str) -> str:
    """"10 lei cashback" -> "10 RON cashback" (titlurile recompenselor în EN);
    text fără " lei" rămâne neschimbat (ex. "Contract de credit")."""
    return re.sub(r"(\d+(?:[.,]\d+)?)\s*lei\b", r"\1 RON", text)


_ESCAPED_PLACEHOLDER_RE = re.compile(r"\\\{([a-z_]+)\\\}")


def _build_reverse_patterns() -> list[tuple[str, re.Pattern[str], list[str]]]:
    """Din fiecare șablon RO din catalog -> un regex ancorat, cu `{name}` ->
    `(?P<name>.+?)` (non-greedy; delimitatorii literali dintre placeholder-e
    dezambiguizează). `re.escape` scapă deja `{`/`}` din șablon."""
    out: list[tuple[str, re.Pattern[str], list[str]]] = []
    for key, entry in NOTIFICATION_MESSAGES.items():
        template = entry["ro"]
        names = _PLACEHOLDER_RE.findall(template)
        pattern = _ESCAPED_PLACEHOLDER_RE.sub(r"(?P<\1>.+?)", re.escape(template))
        out.append((key, re.compile(f"^{pattern}$", re.DOTALL), names))
    return out


_REVERSE_PATTERNS = _build_reverse_patterns()


def render_notification_from_text(stored_text: str, language: Language | None = None) -> str | None:
    """Notificări VECHI (stocate doar ca `text` RO, dinainte de mecanismul
    cheie+params): potrivim `text`-ul înapoi pe un șablon RO din catalog,
    extragem parametrii (sume -> `_minor`+currency, titluri -> ro/en) și
    randăm în limba cerută. `None` dacă nu se potrivește niciun șablon —
    apelantul păstrează atunci `text`-ul original."""
    if not stored_text:
        return None
    text = stored_text.strip()
    for key, regex, names in _REVERSE_PATTERNS:
        m = regex.match(text)
        if not m:
            continue
        params: dict = {}
        ok = True
        for name in names:
            raw = m.group(name)
            if name in _MONEY_PLACEHOLDERS:
                parsed = _parse_money(raw)
                if parsed is None:
                    ok = False
                    break
                params[f"{name}_minor"], params["currency"] = parsed
            elif name in _TITLE_PLACEHOLDERS:
                params["title_ro"] = raw
                params["title_en"] = _lei_to_ron(raw)
            else:
                params[name] = raw
        if ok:
            return render_notification(key, params, language)
    return None


def render_notification(
    message_key: str | None, message_params: dict | None, language: Language | None = None
) -> str | None:
    """Compune textul unei notificări în limba cerută (implicit cea a
    request-ului curent). Întoarce `None` dacă `message_key` lipsește sau nu
    e în catalog — apelantul încearcă atunci `render_notification_from_text`,
    apoi cade pe `text`-ul stocat."""
    if not message_key:
        return None
    entry = NOTIFICATION_MESSAGES.get(message_key)
    if entry is None:
        return None
    lang: Language = language or _current_language.get()
    params = dict(message_params or {})
    currency = str(params.pop("currency", "RON"))
    # `title` cu variante ro/en, când o notificare veche e potrivită înapoi
    # din text (vezi render_notification_from_text)
    if "title_ro" in params or "title_en" in params:
        params["title"] = params.pop("title_en" if lang == "en" else "title_ro", None) or params.pop(
            "title_ro", ""
        ) or params.pop("title_en", "")
        params.pop("title_ro", None)
        params.pop("title_en", None)
    # orice `X_minor` -> `X` formatat ca bani
    for key in [k for k in params if k.endswith("_minor")]:
        params[key[: -len("_minor")]] = _fmt_money(params.pop(key), currency, lang)
    try:
        return (entry.get(lang) or entry["ro"]).format(**params)
    except (KeyError, IndexError):
        return entry["ro"]


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
