"""Traduceri RO/EN pentru mesajele orientate spre utilizator (în principal
`HTTPException.detail` și textul notificărilor trimise prin `_notify_user`)
— citește limba din header-ul `X-Language` trimis de front-end (RO implicit,
identic cu comportamentul de dinainte de această schimbare pentru clienți
vechi/apeluri interne service-to-service care nu trimit header-ul deloc).

Design: un `ContextVar` populat de `LanguageMiddleware` la începutul fiecărui
request, NU un parametru `request: Request` pasat explicit prin fiecare
funcție din service.py — multe funcții de business sunt apelate direct din
teste, fără obiect `Request` (vezi tests/), iar fallback-ul "ro" trebuie să
rămână identic cu comportamentul verificat de acele teste.

Pattern identic cu auth-service/app/i18n.py — vezi acolo pentru contextul
complet al deciziei de design.
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
    # security.py
    "tokenInvalidOrExpired": {"ro": "Token invalid sau expirat.", "en": "Invalid or expired token."},
    "missingAuthorizationHeader": {
        "ro": "Lipsește header-ul Authorization: Bearer <token>.",
        "en": "Missing Authorization header: Bearer <token>.",
    },
    "tokenMissingSubject": {"ro": "Token invalid: lipsește subiectul.", "en": "Invalid token: missing subject."},
    "staffOnly": {"ro": "Acces permis doar personalului.", "en": "Access is allowed for staff only."},
    # service.py — accounts
    "noAccountForUser": {
        "ro": "Nu există niciun cont pentru acest utilizator.",
        "en": "This user has no account.",
    },
    "alreadyHaveAccountType": {
        "ro": "Ai deja un cont {preposition} {label}.",
        "en": "You already have a {label} account.",
    },
    "maxAccountsReached": {
        "ro": "Ai atins numărul maxim de conturi ({max_accounts}).",
        "en": "You've reached the maximum number of accounts ({max_accounts}).",
    },
    "invalidAccountId": {"ro": "ID de cont invalid.", "en": "Invalid account ID."},
    "accountNotFound": {"ro": "Contul nu există.", "en": "This account does not exist."},
    "currentAccountCannotBeDeleted": {
        "ro": "Contul curent nu poate fi șters.",
        "en": "The current account cannot be deleted.",
    },
    "emptyAccountBeforeDelete": {
        "ro": "Golește mai întâi contul (transferă soldul rămas) înainte să-l ștergi.",
        "en": "Empty the account first (transfer the remaining balance) before deleting it.",
    },
    # service.py — cards
    "invalidCardId": {"ro": "ID de card invalid.", "en": "Invalid card ID."},
    "cardNotFound": {"ro": "Cardul nu există.", "en": "This card does not exist."},
    "maxCardsReached": {
        "ro": "Ai atins numărul maxim de carduri ({max_cards}).",
        "en": "You've reached the maximum number of cards ({max_cards}).",
    },
    "insufficientBalancePhysicalCardFee": {
        "ro": "Sold insuficient pentru taxa de emitere a cardului fizic ({fee} RON).",
        "en": "Insufficient balance for the physical card issuance fee ({fee} RON).",
    },
    "passkeyVerificationUnavailable": {
        "ro": "Nu am putut verifica passkey-ul — serviciul de autentificare este indisponibil.",
        "en": "We could not verify the passkey — the authentication service is unavailable.",
    },
    "incorrectPin": {"ro": "PIN incorect.", "en": "Incorrect PIN."},
    "biometricConfirmationFailed": {
        "ro": "Confirmarea biometrică a eșuat.",
        "en": "Biometric confirmation failed.",
    },
    "incorrectCurrentPin": {"ro": "PIN curent incorect.", "en": "Incorrect current PIN."},
    # service.py — pockets
    "invalidPocketId": {"ro": "ID de obiectiv invalid.", "en": "Invalid goal ID."},
    "pocketNotFound": {"ro": "Obiectivul nu există.", "en": "This goal does not exist."},
    "amountExceedsAvailableBalance": {
        "ro": "Suma depășește soldul disponibil (neluat deja de alte obiective).",
        "en": "The amount exceeds the available balance (not already allocated to other goals).",
    },
    "cannotWithdrawMoreThanSaved": {
        "ro": "Nu poți retrage mai mult decât ai economisit.",
        "en": "You cannot withdraw more than you've saved.",
    },
    "withdrawSavingsBeforeDelete": {
        "ro": "Retrage banii economisiți înainte să ștergi obiectivul.",
        "en": "Withdraw the saved money before deleting the goal.",
    },
    # service.py — beneficiaries
    "invalidBeneficiaryId": {"ro": "ID de beneficiar invalid.", "en": "Invalid beneficiary ID."},
    "beneficiaryNotFound": {"ro": "Beneficiarul nu există.", "en": "This beneficiary does not exist."},
    # service.py — internal (service-to-service)
    "userAlreadyProvisioned": {
        "ro": "Userul are deja un cont provizionat.",
        "en": "This user already has a provisioned account.",
    },
    "noAccountForUserId": {
        "ro": "Nu există cont pentru acest user_id.",
        "en": "There is no account for this user_id.",
    },
    "insufficientBalanceOrInactiveAccount": {
        "ro": "Sold insuficient sau cont inactiv/inexistent.",
        "en": "Insufficient balance, or the account is inactive/nonexistent.",
    },
    "accountNotFoundOrInactive": {
        "ro": "Cont inexistent sau inactiv.",
        "en": "The account does not exist or is inactive.",
    },
    "noAccountOfType": {
        "ro": "Nu ai un cont de tipul '{account_type}'.",
        "en": "You don't have an account of type '{account_type}'.",
    },
    "noAccountForIban": {
        "ro": "Nu există niciun cont cu acest IBAN.",
        "en": "There is no account with this IBAN.",
    },
    "insufficientBalanceOrInactiveSourceAccount": {
        "ro": "Sold insuficient sau cont sursă inactiv/inexistent.",
        "en": "Insufficient balance, or the source account is inactive/nonexistent.",
    },
    "destinationAccountInactiveTransferCancelled": {
        "ro": "Cont destinație inactiv sau inexistent — transfer anulat.",
        "en": "Destination account inactive or nonexistent — transfer cancelled.",
    },
    "noCurrencyAccountYet": {
        "ro": "Nu ai încă un cont pentru moneda asta — deschide unul din pagina Conturi înainte de a schimba valută.",
        "en": "You don't have an account for this currency yet — open one from the Accounts page before exchanging currency.",
    },
    "insufficientBalanceSourceInactiveExchange": {
        "ro": "Sold insuficient sau cont sursă inactiv.",
        "en": "Insufficient balance, or the source account is inactive.",
    },
    "destinationAccountInactiveExchangeCancelled": {
        "ro": "Cont destinație inactiv — schimb anulat.",
        "en": "Destination account inactive — exchange cancelled.",
    },
    # notifications (_notify_user)
    "cardBlockedNotification": {
        "ro": "Cardul terminat în {last_four} a fost blocat.",
        "en": "The card ending in {last_four} has been blocked.",
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
