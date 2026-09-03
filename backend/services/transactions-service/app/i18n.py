"""Traduceri RO/EN pentru mesajele orientate spre utilizator (`HTTPException.
detail`, textul notificărilor proactive trimise către support-service) —
citește limba din header-ul `X-Language` trimis de front-end (RO implicit,
identic cu comportamentul de dinainte de această schimbare pentru clienți
vechi/apeluri interne service-to-service care nu trimit header-ul deloc).

Design: un `ContextVar` populat de `LanguageMiddleware` la începutul fiecărui
request, NU un parametru `request: Request` pasat explicit prin fiecare
funcție din service.py — multe funcții de business sunt apelate direct din
teste, fără obiect `Request` (vezi tests/test_transfers.py), iar fallback-ul
"ro" trebuie să rămână identic cu comportamentul verificat de acele teste.

Excepție notabilă la propagarea ContextVar-ului: `create_transfer` (app/
service.py) programează `guardian_service.generate_guardian_explanations` prin
`BackgroundTasks.add_task`, care rulează DUPĂ ce răspunsul a fost deja trimis
— ContextVar-ul NU se propagă fiabil acolo. Limba trebuie captată sincron,
ÎNAINTE de `add_task`, cu `current_language()`, și pasată explicit ca
parametru — vezi service.py și app/guardian/service.py.

`app/scheduler.py` (transferuri programate/expirare hold, loop-uri asyncio
interne, fără request HTTP) nu populează niciodată acest ContextVar — cade
implicit pe "ro", corect: un tick de scheduler nu are un user/limbă asociată.
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
    # --- accounts-service cross-calls (service.py, holds.py) ---------------
    "accountsServiceUnavailable": {
        "ro": "accounts-service indisponibil.",
        "en": "accounts-service is unavailable.",
    },
    "accountsServiceQueryError": {
        "ro": "Eroare la interogarea accounts-service.",
        "en": "Error querying accounts-service.",
    },
    # --- Reîncărcare telefon — verificare Twilio Lookup (service.py::
    # _verify_topup_phone). Blocăm DOAR pe „nu e mobil" (cert); o
    # nepotrivire de operator e doar avertisment (content_warning), vezi
    # comentariul din service.py despre nume legale vs. branduri.
    "topupNotMobileNumber": {
        "ro": "Acest număr nu pare a fi de telefon mobil — nu poate primi reîncărcare de credit.",
        "en": "This number does not appear to be a mobile number — it cannot receive a top-up.",
    },
    "topupOperatorMismatchWarning": {
        "ro": "Numărul pare să aparțină de {detected}, nu operatorul selectat — verifică înainte de a continua.",
        "en": "The number appears to belong to {detected}, not the selected operator — please double-check.",
    },
    "noAccountForUser": {
        "ro": "Nu există un cont pentru utilizatorul curent.",
        "en": "There is no account for the current user.",
    },
    "insufficientBalanceOrInactiveAccount": {
        "ro": "Sold insuficient sau cont inactiv.",
        "en": "Insufficient balance or inactive account.",
    },
    "transferApplyError": {
        "ro": "Eroare la aplicarea transferului în accounts-service.",
        "en": "Error applying the transfer in accounts-service.",
    },
    "accountNotFound": {"ro": "Cont inexistent.", "en": "This account does not exist."},

    # --- create_transfer validation (service.py) ----------------------------
    "sourceAccountNotActive": {"ro": "Contul sursă nu este activ.", "en": "The source account is not active."},
    "destinationAccountNotFound": {
        "ro": "Contul destinație nu există.",
        "en": "The destination account does not exist.",
    },
    "destinationAccountNotActive": {
        "ro": "Contul destinație nu este activ.",
        "en": "The destination account is not active.",
    },
    "currencyMismatch": {
        "ro": "Monedele conturilor sursă și destinație diferă.",
        "en": "The source and destination account currencies differ.",
    },
    "insufficientBalance": {"ro": "Sold insuficient.", "en": "Insufficient balance."},
    "sameAccountTransfer": {
        "ro": "Nu poți transfera către același cont.",
        "en": "You cannot transfer to the same account.",
    },
    "paymentConfirmationRequired": {
        "ro": "Transferurile peste {threshold} {currency} necesită confirmare cu PIN-ul cardului.",
        "en": "Transfers over {threshold} {currency} require confirmation with the card PIN.",
    },
    "incorrectPin": {"ro": "PIN incorect.", "en": "Incorrect PIN."},
    "beneficiaryBlocklisted": {
        "ro": "Acest beneficiar este pe lista de blocare a băncii.",
        "en": "This beneficiary is on the bank's block list.",
    },

    # --- transactions lookups (service.py, shared with holds.py) -----------
    "transactionNotFound": {"ro": "Tranzacție inexistentă.", "en": "This transaction does not exist."},
    "transactionDoesNotExist": {"ro": "Tranzacția nu există.", "en": "This transaction does not exist."},
    "invalidTransactionId": {"ro": "ID de tranzacție invalid.", "en": "Invalid transaction ID."},

    # --- scheduled transfers -------------------------------------------------
    "invalidScheduledTransferId": {
        "ro": "ID de transfer programat invalid.",
        "en": "Invalid scheduled transfer ID.",
    },
    "scheduledTransferNotFound": {
        "ro": "Transferul programat nu există.",
        "en": "The scheduled transfer does not exist.",
    },

    # --- payment requests ------------------------------------------------------
    "yourAccountNotActive": {"ro": "Contul tău nu este activ.", "en": "Your account is not active."},
    "paymentRequestDescriptionFlagged": {
        "ro": "Descrierea conține termeni asociați cu activități ilegale/violente — reformuleaz-o ca să poți crea cererea.",
        "en": "The description contains terms associated with illegal/violent activity — please rephrase it to create the request.",
    },
    "paymentRequestNotFound": {"ro": "Cerere de plată inexistentă.", "en": "This payment request does not exist."},
    "paymentRequestNotActive": {
        "ro": "Această cerere de plată nu mai este activă.",
        "en": "This payment request is no longer active.",
    },
    "cannotPayOwnRequest": {
        "ro": "Nu poți plăti propria cerere de plată.",
        "en": "You cannot pay your own payment request.",
    },
    "paymentRequestJustClaimed": {
        "ro": "Această cerere de plată tocmai a fost plătită sau anulată.",
        "en": "This payment request was just paid or cancelled.",
    },

    # --- statement -------------------------------------------------------------
    "startDateBeforeEndDate": {
        "ro": "Data de start trebuie să fie înaintea datei de final.",
        "en": "The start date must be before the end date.",
    },

    # --- holds.py ----------------------------------------------------------------
    "holdingAccountResolutionError": {
        "ro": "Eroare la rezolvarea contului de reținere.",
        "en": "Error resolving the holding account.",
    },
    "fundsMovementError": {
        "ro": "Eroare la aplicarea mutării de fonduri.",
        "en": "Error applying the funds movement.",
    },
    "insufficientBalanceOrInactiveSourceAccount": {
        "ro": "Sold insuficient sau cont sursă inactiv.",
        "en": "Insufficient balance or inactive source account.",
    },
    "holdNoLongerPending": {
        "ro": "Această reținere nu (mai) este în așteptare.",
        "en": "This hold is no longer pending.",
    },
    "holdResolutionError": {
        "ro": "Eroare la rezolvarea reținerii — contactează suportul.",
        "en": "Error resolving the hold — please contact support.",
    },

    # --- security.py (JWT) --------------------------------------------------
    "tokenInvalidOrExpired": {"ro": "Token invalid sau expirat.", "en": "Invalid or expired token."},
    "missingAuthorizationHeader": {
        "ro": "Lipsește header-ul Authorization: Bearer <token>.",
        "en": "Missing Authorization header: Bearer <token>.",
    },
    "tokenMissingSubject": {"ro": "Token invalid: lipsește subiectul.", "en": "Invalid token: missing subject."},
    "staffOnlyAccess": {"ro": "Acces permis doar personalului.", "en": "Access is restricted to staff."},

    # --- blocklist.py ---------------------------------------------------------
    "invalidId": {"ro": "ID invalid.", "en": "Invalid ID."},
    "entryNotFound": {"ro": "Intrarea nu există.", "en": "This entry does not exist."},

    # --- fraud/staff.py ---------------------------------------------------------
    "evaluationNotFound": {"ro": "Evaluare inexistentă.", "en": "This evaluation does not exist."},
    "evaluationAlreadyReviewed": {
        "ro": "Această evaluare a fost deja revizuită.",
        "en": "This evaluation has already been reviewed.",
    },

    # --- content_screening.py (avertisment static, NU listele de cuvinte) ---
    "contentWarningMessage": {
        "ro": "Descrierea conține termeni asociați cu activități ilegale/violente. Te rugăm să reformulezi dacă a fost o confuzie.",
        "en": "The description contains terms associated with illegal/violent activity. Please rephrase it if this was a misunderstanding.",
    },

    # --- notificări proactive (service.py::_notify_user call sites) --------
    "transferHoldNotification": {
        "ro": "Transferul de {amount} {currency} către {iban} este în verificare de securitate — vei fi anunțat imediat ce e rezolvat.",
        "en": "Your transfer of {amount} {currency} to {iban} is under security review — you'll be notified as soon as it's resolved.",
    },
    "transferSuccessNotification": {
        "ro": "Transfer de {amount} {currency} către {iban} — reușit.",
        "en": "Transfer of {amount} {currency} to {iban} — successful.",
    },
    "transferReceivedNotification": {
        "ro": "Ai primit {amount} {currency} de la {name}.",
        "en": "You received {amount} {currency} from {name}.",
    },
    "transferHoldCancelledNotification": {
        "ro": "Ai anulat transferul reținut — fondurile au revenit în cont.",
        "en": "You cancelled the held transfer — the funds have returned to your account.",
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
