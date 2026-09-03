"""Teste pentru app/services/trip_estimate_service.py::build_trip_estimate —
funcție PURĂ care construiește estimarea de cost de vacanță (doar zbor,
deja convertit în RON) dintr-un rezultat Duffel. Apelurile efective către
Duffel (app/duffel_client.py) și conversia valutară
(app/tools/exchange_tools.py) NU sunt reluate aici — vezi test_registry.py
pentru dispatch-ul tool-ului, mock-uit la graniță.

NOTĂ: acest fișier NU atinge nicio bază de date (funcții Python pure) —
categoric diferit de test_forecast_analytics.py (transactions-service),
care are fixture-uri `autouse` ce ating Mongo real dacă rulează neizolat.
"""

from datetime import date

from app.duffel_client import FlightEstimate
from app.services.trip_estimate_service import build_trip_estimate


def test_no_flight_data_marks_unavailable():
    result = build_trip_estimate(
        destination_city="Barcelona",
        departure_date="2026-12-01",
        return_date="2026-12-08",
        travelers=1,
        flight=None,
        flight_total_ron_minor=None,
    )
    assert result == {"available": False, "reason": "no_flight_data", "destination_city": "Barcelona"}


def test_conversion_failure_also_marks_unavailable():
    # Zborul real a fost găsit, dar conversia valutară a eșuat — nu arătăm
    # un total într-o valută greșită, nici unul lipsă tratat ca 0.
    flight = FlightEstimate(price_minor=16482, currency="EUR", airline="Iberia")
    result = build_trip_estimate(
        destination_city="Barcelona",
        departure_date="2026-12-01",
        return_date="2026-12-08",
        travelers=1,
        flight=flight,
        flight_total_ron_minor=None,
    )
    assert result["available"] is False


def test_available_estimate_uses_converted_ron_total():
    flight = FlightEstimate(price_minor=16482, currency="EUR", airline="Iberia")
    result = build_trip_estimate(
        destination_city="Barcelona",
        departure_date="2026-12-01",
        return_date="2026-12-08",
        travelers=1,
        flight=flight,
        flight_total_ron_minor=82000,
        applied_rate=4.9756,
    )
    assert result["available"] is True
    assert result["total_estimate_minor"] == 82000
    assert result["flight"] == {
        "airline": "Iberia",
        "original_price": "164.82 EUR",
        "applied_exchange_rate": 4.9756,
        "total_ron_minor": 82000,
    }


def test_ron_flight_has_no_applied_rate():
    # Zborul deja în RON — nicio conversie, deci niciun curs de aplicat.
    flight = FlightEstimate(price_minor=120000, currency="RON", airline="Wizz Air")
    result = build_trip_estimate(
        destination_city="Barcelona",
        departure_date="2026-12-01",
        return_date="2026-12-08",
        travelers=1,
        flight=flight,
        flight_total_ron_minor=120000,
    )
    assert result["flight"]["applied_exchange_rate"] is None


# --- savings_plan (raportat de user: "pare la fel dacă e ianuarie sau ---
# --- peste o săptămână") --------------------------------------------------


def test_savings_plan_urgent_when_less_than_30_days_away():
    flight = FlightEstimate(price_minor=90000, currency="RON", airline="Wizz Air")
    result = build_trip_estimate(
        destination_city="Barcelona",
        departure_date="2026-01-10",
        return_date="2026-01-15",
        travelers=1,
        flight=flight,
        flight_total_ron_minor=90000,
        today=date(2026, 1, 5),  # 5 zile până la plecare
    )
    assert result["savings_plan"] == {
        "urgent": True,
        "days_until_departure": 5,
        "months_until_departure": None,
        "suggested_monthly_saving_minor": None,
    }


def test_savings_plan_suggests_monthly_amount_when_far_away():
    flight = FlightEstimate(price_minor=90000, currency="RON", airline="Wizz Air")
    result = build_trip_estimate(
        destination_city="Barcelona",
        departure_date="2026-05-01",
        return_date="2026-05-08",
        travelers=1,
        flight=flight,
        flight_total_ron_minor=90000,
        today=date(2026, 1, 1),  # 4 luni până la plecare
    )
    plan = result["savings_plan"]
    assert plan["urgent"] is False
    assert plan["months_until_departure"] == 4
    assert plan["suggested_monthly_saving_minor"] == round(90000 / 4)


def test_savings_plan_a_week_away_differs_from_months_away():
    """Exact scenariul raportat — o săptămână și câteva luni NU trebuie să
    dea același rezultat."""
    flight = FlightEstimate(price_minor=90000, currency="RON", airline="Wizz Air")

    soon = build_trip_estimate(
        destination_city="Barcelona", departure_date="2026-01-08", return_date="2026-01-15",
        travelers=1, flight=flight, flight_total_ron_minor=90000, today=date(2026, 1, 1),
    )
    later = build_trip_estimate(
        destination_city="Barcelona", departure_date="2026-07-01", return_date="2026-07-08",
        travelers=1, flight=flight, flight_total_ron_minor=90000, today=date(2026, 1, 1),
    )

    assert soon["savings_plan"] != later["savings_plan"]
    assert soon["savings_plan"]["urgent"] is True
    assert later["savings_plan"]["urgent"] is False


def test_savings_plan_none_on_unparsable_departure_date():
    flight = FlightEstimate(price_minor=90000, currency="RON", airline="Wizz Air")
    result = build_trip_estimate(
        destination_city="Barcelona",
        departure_date="cine știe când",
        return_date="2026-01-15",
        travelers=1,
        flight=flight,
        flight_total_ron_minor=90000,
    )
    assert result["savings_plan"] is None
