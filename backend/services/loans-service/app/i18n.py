"""Traduceri RO/EN pentru mesajele orientate spre utilizator (`HTTPException.
detail`, motivul de respingere a cererii de credit, textul notificărilor) —
citește limba din header-ul `X-Language` trimis de front-end (RO implicit,
identic cu comportamentul de dinainte pentru apeluri interne / clienți vechi
care nu trimit header-ul).

Design: `ContextVar` populat de `LanguageMiddleware` la începutul fiecărui
request. Notificările din `app/scheduler.py` (loop asyncio intern, fără
request HTTP) cad implicit pe "ro" — corect, un tick de scheduler nu are un
user/limbă asociată.

Vezi transactions-service/app/i18n.py pentru implementarea de referință.
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
    async def dispatch(self, request: Request, call_next) -> Response:
        raw = (request.headers.get("x-language") or "ro").lower()
        token = _current_language.set(raw if raw in ("ro", "en") else "ro")
        try:
            return await call_next(request)
        finally:
            _current_language.reset(token)


def current_language() -> Language:
    return _current_language.get()


T: dict[str, dict[Language, str]] = {
    # --- security.py (JWT) ---------------------------------------------------
    "tokenInvalidOrExpired": {"ro": "Token invalid sau expirat.", "en": "Invalid or expired token."},
    "missingAuthorizationHeader": {
        "ro": "Lipsește header-ul Authorization: Bearer <token>.",
        "en": "Missing Authorization header: Bearer <token>.",
    },
    "tokenMissingSubject": {"ro": "Token invalid: lipsește subiectul.", "en": "Invalid token: missing subject."},
    # --- cross-service calls ----------------------------------------------
    "accountsServiceUnavailable": {"ro": "accounts-service indisponibil.", "en": "accounts-service is unavailable."},
    "accountsServiceQueryError": {
        "ro": "Eroare la interogarea accounts-service.",
        "en": "Error querying accounts-service.",
    },
    "transactionsServiceUnavailable": {
        "ro": "transactions-service indisponibil.",
        "en": "transactions-service is unavailable.",
    },
    "transactionsServiceQueryError": {
        "ro": "Eroare la interogarea transactions-service.",
        "en": "Error querying transactions-service.",
    },
    "currentAccountNotFound": {"ro": "Nu am găsit contul tău curent.", "en": "We couldn't find your current account."},
    "accountDebitError": {"ro": "Eroare la debitarea contului.", "en": "Error debiting the account."},
    "accountCreditError": {"ro": "Eroare la creditarea contului.", "en": "Error crediting the account."},
    # --- apply / payoff (service.py) -------------------------------------
    "amountOutOfRange": {
        "ro": "Suma trebuie să fie între {min} și {max} RON.",
        "en": "The amount must be between {min} and {max} RON.",
    },
    "loanNotFound": {"ro": "Credit inexistent.", "en": "This loan does not exist."},
    "loanNoLongerActive": {"ro": "Creditul nu mai este activ.", "en": "The loan is no longer active."},
    "insufficientBalanceForPayoff": {
        "ro": "Sold insuficient pentru plata anticipată.",
        "en": "Insufficient balance for the early payoff.",
    },
    # --- eligibility.py: motive de respingere ---------------------------
    "rejectNoIncomeHistory": {
        "ro": 'Nu am găsit niciun venit înregistrat (categoria "Venit") în ultimele {days} de zile — nu putem evalua o cerere de credit fără istoric de venit.',
        "en": 'We found no recorded income (the "Income" category) in the last {days} days — we can\'t assess a loan application without income history.',
    },
    "rejectInstalmentTooHigh": {
        "ro": "Rata lunară de {instalment} depășește ce-ți poți permite: venitul tău mediu lunar e {income}, iar politica MaestroBank limitează ratele lunare (inclusiv la creditele deja active) la {percent}% din venit — adică {available} disponibili acum. Încearcă o sumă mai mică sau un termen mai lung.",
        "en": "The monthly instalment of {instalment} exceeds what you can afford: your average monthly income is {income}, and MaestroBank policy caps monthly instalments (including active loans) at {percent}% of income — that is {available} available now. Try a smaller amount or a longer term.",
    },
    # --- notificări proactive (service.py) -----------------------------
    "loanApprovedNotification": {
        "ro": "Creditul tău de {amount} a fost aprobat — rata lunară e {instalment}, pe {months} luni.",
        "en": "Your loan of {amount} was approved — the monthly instalment is {instalment}, over {months} months.",
    },
    "loanPaidOffEarlyNotification": {
        "ro": "Ai plătit anticipat restul de {amount} — creditul e închis.",
        "en": "You paid off the remaining {amount} early — the loan is closed.",
    },
    "loanPaymentMissedNotification": {
        "ro": "Rata de {amount} nu a putut fi plătită — sold insuficient. Reîncercăm automat.",
        "en": "The {amount} instalment could not be paid — insufficient balance. We'll retry automatically.",
    },
    "loanPaymentNotification": {
        "ro": "Rata de {amount} a fost plătită automat.",
        "en": "The {amount} instalment was paid automatically.",
    },
    "loanClosedNotification": {
        "ro": "Ultima rată a fost plătită — creditul e închis.",
        "en": "The final instalment was paid — the loan is closed.",
    },
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


def format_ron(amount_minor: int) -> str:
    """"1234,50 lei" (ro) / "1234.50 RON" (en) — DOAR pentru textul din
    motivele de respingere / notificări, nu pentru UI (frontend-ul are
    MoneyPipe)."""
    sign = "-" if amount_minor < 0 else ""
    major, minor = divmod(abs(amount_minor), 100)
    if _current_language.get() == "en":
        return f"{sign}{major}.{minor:02d} RON"
    return f"{sign}{major},{minor:02d} lei"
