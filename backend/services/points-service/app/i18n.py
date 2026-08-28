"""Traduceri RO/EN pentru textul orientat spre utilizator (`HTTPException.
detail`, textul notificărilor) plus alegerea variantei RO/EN pentru
catalogul de recompense și segmentele roții — citește limba din header-ul
`X-Language` (RO implicit).

Design: `ContextVar` populat de `LanguageMiddleware`. Vezi
transactions-service/app/i18n.py pentru implementarea de referință.
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


def localized(item: dict, field: str) -> str:
    """`item[field]` (ro) sau `item[field + "_en"]` (en) — pentru catalogul
    de recompense (title/description) și segmentele roții (label), unde
    varianta EN e co-locată în același dict (vezi app/rewards_catalog.py,
    app/wheel_segments.py)."""
    if _current_language.get() == "en":
        return item.get(f"{field}_en") or item[field]
    return item[field]


def format_ron(amount_minor: int) -> str:
    """"12,50 lei" (ro) / "12.50 RON" (en) — doar pentru textul din
    notificări, nu pentru UI."""
    sign = "-" if amount_minor < 0 else ""
    major, minor = divmod(abs(amount_minor), 100)
    if _current_language.get() == "en":
        return f"{sign}{major}.{minor:02d} RON"
    return f"{sign}{major},{minor:02d} lei"


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
    "currentAccountNotFound": {"ro": "Nu am găsit contul tău curent.", "en": "We couldn't find your current account."},
    "accountCreditError": {"ro": "Eroare la creditarea contului.", "en": "Error crediting the account."},
    # --- service.py -----------------------------------------------------
    "welcomeBonusAlreadyClaimed": {
        "ro": "Ai revendicat deja bonusul de bun-venit.",
        "en": "You have already claimed the welcome bonus.",
    },
    "rewardNotFound": {"ro": "Recompensă inexistentă.", "en": "This reward does not exist."},
    "notEnoughPointsForReward": {
        "ro": "Nu ai suficiente puncte pentru această recompensă.",
        "en": "You don't have enough points for this reward.",
    },
    "notEnoughPointsForWager": {
        "ro": "Nu ai suficiente puncte pentru acest pariu.",
        "en": "You don't have enough points for this wager.",
    },
    # --- notificări proactive -----------------------------------------
    "welcomeBonusNotification": {
        "ro": "Ai primit {points} puncte de bun-venit — le poți folosi direct pentru o recompensă.",
        "en": "You received {points} welcome points — you can use them right away for a reward.",
    },
    "rewardRedeemedNotification": {
        "ro": 'Ai răscumpărat "{title}" — {amount} creditați în cont.',
        "en": 'You redeemed "{title}" — {amount} credited to your account.',
    },
    "wheelWinNotification": {
        "ro": "Ai câștigat {amount} la roata norocului!",
        "en": "You won {amount} on the wheel of fortune!",
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
