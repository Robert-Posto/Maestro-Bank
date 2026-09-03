"""Wrapper subțire peste Twilio Lookup v2 (`Fields=line_type_intelligence`) —
verifică REAL cărui operator îi aparține un număr de telefon, la o
reîncărcare (vezi service.py::_verify_topup_phone). NU e SDK-ul oficial
Twilio, doar un apel GET cu autentificare Basic — exact ca restul
clienților externi subțiri din acest serviciu (vezi guardian/llm_client.py
pentru același principiu: o eroare NU are voie să urce, degradează tăcut la
"neverificat" — apelantul decide ce înseamnă asta pentru reîncărcare).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.config import settings

logger = logging.getLogger("transactions-service")

_LOOKUP_URL_TEMPLATE = "https://lookups.twilio.com/v2/PhoneNumbers/{phone_number}"


@dataclass
class CarrierLookupResult:
    carrier_name: str | None
    line_type: str | None


async def lookup_carrier(phone_number_e164: str) -> CarrierLookupResult | None:
    """None înseamnă „neverificat" — apelantul (service.py) distinge separat
    „Twilio neconfigurat" de „apelul a eșuat" via `settings.twilio_configured`,
    ca userul să vadă mereu DE CE n-a fost verificat, nu doar o tăcere
    identică unui succes."""
    if not settings.twilio_configured:
        return None

    async with httpx.AsyncClient(
        timeout=settings.twilio_lookup_timeout_seconds,
        auth=(settings.twilio_account_sid, settings.twilio_auth_token),
    ) as client:
        try:
            response = await client.get(
                _LOOKUP_URL_TEMPLATE.format(phone_number=phone_number_e164),
                params={"Fields": "line_type_intelligence"},
            )
        except httpx.RequestError as exc:
            logger.warning("transactions-service: Twilio Lookup indisponibil (rețea): %s", exc)
            return None

    if response.status_code != 200:
        logger.warning("transactions-service: Twilio Lookup a răspuns %d pentru un request de verificare", response.status_code)
        return None

    data = response.json()
    line_type_intelligence = data.get("line_type_intelligence") or {}
    return CarrierLookupResult(
        carrier_name=line_type_intelligence.get("carrier_name"),
        line_type=line_type_intelligence.get("type"),
    )
