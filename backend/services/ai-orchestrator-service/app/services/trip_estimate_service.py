"""Construiește estimarea de cost de vacanță (doar zbor, pentru acum — vezi
app/tools/registry.py::estimate_trip_cost) dintr-un preț REAL Duffel deja
convertit în RON — funcție PURĂ (fără I/O), apelată DUPĂ ce zborul a fost
căutat (app/duffel_client.py) și convertit (app/tools/exchange_tools.py).

Cazarea NU e inclusă — nu e o simplificare temporară, ci o limitare
comercială REALĂ: Stays (cazări) pe Duffel e o funcție activată doar cu
cont de business plătit (verificat live: 403 "This feature is not enabled
for your account"), spre deosebire de căutarea de zboruri, care e liberă.

`applied_rate` e inclus explicit (nu doar totalul deja convertit) — ca
agentul să poată explica REAL "de unde a scos suma" dacă userul întreabă,
nu doar să repete cifra finală. None dacă zborul a fost deja în RON (nicio
conversie necesară).

`savings_plan` (raportat de user: "pare că pentru el e cam aceeași chestie
dacă e ianuarie sau peste o săptămână") — calculat AICI, determinist (NU
lăsat pe seama aritmeticii de date a GPT), din timpul REAL rămas până la
plecare: o sumă lunară sugerată dacă mai sunt cel puțin 30 de zile, sau un
semnal explicit de urgență dacă vacanța e prea aproape ca să mai aibă sens
o economisire treptată.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from app.duffel_client import FlightEstimate

# Sub 30 de zile rămase, o "sumă lunară" de economisit nu mai are sens practic
# — mai aproape de "trebuie pusă deoparte toată suma acum" decât de un plan.
_URGENT_THRESHOLD_DAYS = 30


def _build_savings_plan(departure_date: str, total_estimate_minor: int, today: date | None = None) -> dict | None:
    """None DOAR dacă `departure_date` nu poate fi interpretat (GPT a trimis
    ceva neconform formatului YYYY-MM-DD cerut în schema tool-ului) — nu
    lăsăm asta să pice tot răspunsul, doar omitem planul de economisire."""
    today = today or datetime.now(timezone.utc).date()
    try:
        departure = date.fromisoformat(departure_date)
    except ValueError:
        return None

    days_until_departure = max((departure - today).days, 0)

    if days_until_departure < _URGENT_THRESHOLD_DAYS:
        return {
            "urgent": True,
            "days_until_departure": days_until_departure,
            "months_until_departure": None,
            "suggested_monthly_saving_minor": None,
        }

    months_until_departure = max(round(days_until_departure / 30), 1)
    return {
        "urgent": False,
        "days_until_departure": days_until_departure,
        "months_until_departure": months_until_departure,
        "suggested_monthly_saving_minor": round(total_estimate_minor / months_until_departure),
    }


def build_trip_estimate(
    destination_city: str,
    departure_date: str,
    return_date: str,
    travelers: int,
    flight: FlightEstimate | None,
    flight_total_ron_minor: int | None,
    applied_rate: float | None = None,
    today: date | None = None,
) -> dict:
    if flight is None or flight_total_ron_minor is None:
        return {
            "available": False,
            "reason": "no_flight_data",
            "destination_city": destination_city,
        }

    return {
        "available": True,
        "destination_city": destination_city,
        "departure_date": departure_date,
        "return_date": return_date,
        "travelers": travelers,
        "flight": {
            "airline": flight.airline,
            "original_price": f"{flight.price_minor / 100:.2f} {flight.currency}",
            "applied_exchange_rate": applied_rate,
            "total_ron_minor": flight_total_ron_minor,
        },
        "total_estimate_minor": flight_total_ron_minor,
        "savings_plan": _build_savings_plan(departure_date, flight_total_ron_minor, today),
        "note": (
            "Estimare doar pentru zbor. Cazarea nu poate fi căutată — Stays pe Duffel "
            "necesită cont de business plătit, nu e disponibilă cu acest cont."
        ),
    }
