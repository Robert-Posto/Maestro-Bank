"""Wrapper subțire peste Duffel (`api.duffel.com`) — preț REAL de zbor
pentru `estimate_trip_cost` (vezi app/tools/registry.py). Un token de test
(`duffel_test_...`) întoarce oferte reale (tarife/companii reale) fără să
poată crea vreo comandă/plată reală — vezi config.py pentru de ce Duffel,
nu Amadeus (program închis).

Filozofie identică restului serviciului (Guardian, Twilio Lookup): o
eroare/lipsă de configurare NU are voie să urce — degradează la
"indisponibil", apelantul (app/tools/registry.py) decide ce înseamnă asta
pentru răspunsul agentului (NU inventează un preț dacă nu avem unul real).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.config import settings

logger = logging.getLogger("ai-orchestrator-service.duffel")

_OFFER_REQUESTS_PATH = "/air/offer_requests"


@dataclass
class FlightEstimate:
    # Preț TOTAL pentru tot itinerariul cerut (dus-întors, dacă s-au trimis
    # 2 slice-uri) — Duffel întoarce mereu prețul complet al ofertei, NU
    # per segment/direcție.
    price_minor: int
    currency: str
    airline: str


async def search_cheapest_flight(
    origin_iata: str, destination_iata: str, departure_date: str, return_date: str, adults: int
) -> FlightEstimate | None:
    if not settings.duffel_configured:
        return None

    async with httpx.AsyncClient(base_url=settings.duffel_base_url, timeout=settings.duffel_request_timeout_seconds) as client:
        try:
            response = await client.post(
                _OFFER_REQUESTS_PATH,
                params={"return_offers": "true"},
                headers={
                    "Authorization": f"Bearer {settings.duffel_access_token}",
                    "Duffel-Version": settings.duffel_api_version,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={
                    "data": {
                        "slices": [
                            {"origin": origin_iata, "destination": destination_iata, "departure_date": departure_date},
                            {"origin": destination_iata, "destination": origin_iata, "departure_date": return_date},
                        ],
                        "passengers": [{"type": "adult"} for _ in range(max(1, adults))],
                        "cabin_class": "economy",
                    }
                },
            )
        except httpx.RequestError as exc:
            logger.warning("duffel: căutare zbor eșuată (rețea): %s", exc)
            return None

        if response.status_code not in (200, 201):
            logger.warning("duffel: căutare zbor a răspuns %d", response.status_code)
            return None

        offers = (response.json().get("data") or {}).get("offers") or []
        if not offers:
            return None

        cheapest = min(offers, key=lambda offer: float(offer["total_amount"]))
        airline_name = cheapest["slices"][0]["segments"][0]["marketing_carrier"]["name"]

        return FlightEstimate(
            price_minor=round(float(cheapest["total_amount"]) * 100),
            currency=cheapest["total_currency"],
            airline=airline_name,
        )
