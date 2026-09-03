"""Teste pentru app/tools/registry.py — conversia RON -> bani/subunități
(_to_minor) și dispatch-ul tool-urilor de estimare/economisire pentru
vacanțe (estimate_trip_cost / propose_create_savings_pocket), mock-uite la
graniță (app.duffel_client / app.tools.exchange_tools) — apelurile HTTP
reale sunt izolate acolo, vezi test_trip_estimate_service.py pentru logica
pură de construire a estimării."""

import pytest

from app.duffel_client import FlightEstimate
from app.tools.errors import ToolError
from app.tools.registry import ToolResultCache, _to_minor, execute_tool


def test_to_minor_converts_whole_number():
    assert _to_minor(2000, "x") == 200000


def test_to_minor_converts_decimal():
    assert _to_minor(799.99, "x") == 79999


def test_to_minor_accepts_numeric_string():
    # unele modele trimit uneori numărul ca string în JSON — tot valid.
    assert _to_minor("500", "x") == 50000


def test_to_minor_rejects_non_numeric_value():
    with pytest.raises(ToolError):
        _to_minor("mult", "requested_amount_ron")


def test_to_minor_rejects_none():
    with pytest.raises(ToolError):
        _to_minor(None, "requested_amount_ron")


# --- estimate_trip_cost -------------------------------------------------


_TRIP_ARGS = {
    "destination_city": "Barcelona",
    "destination_iata": "BCN",
    "departure_date": "2026-12-01",
    "return_date": "2026-12-08",
}


async def test_estimate_trip_cost_not_configured(monkeypatch):
    monkeypatch.setattr("app.tools.registry.settings.duffel_access_token", "")

    result = await execute_tool("estimate_trip_cost", _TRIP_ARGS, "Bearer token", ToolResultCache())

    assert result == {"available": False, "reason": "not_configured"}


async def test_estimate_trip_cost_ron_flight_skips_conversion_call(monkeypatch):
    monkeypatch.setattr("app.tools.registry.settings.duffel_access_token", "token")

    async def fake_flight(**kwargs):
        assert kwargs["origin_iata"] == "OTP"
        assert kwargs["destination_iata"] == "BCN"
        return FlightEstimate(price_minor=120000, currency="RON", airline="Wizz Air")

    async def fake_quote(*args, **kwargs):
        raise AssertionError("nu trebuie apelată conversia dacă zborul e deja în RON")

    monkeypatch.setattr("app.tools.registry.duffel_client.search_cheapest_flight", fake_flight)
    monkeypatch.setattr("app.tools.registry.exchange_tools.get_quote", fake_quote)

    result = await execute_tool("estimate_trip_cost", _TRIP_ARGS, "Bearer token", ToolResultCache())

    assert result["available"] is True
    assert result["total_estimate_minor"] == 120000


async def test_estimate_trip_cost_converts_non_ron_flight(monkeypatch):
    monkeypatch.setattr("app.tools.registry.settings.duffel_access_token", "token")

    async def fake_flight(**kwargs):
        return FlightEstimate(price_minor=16482, currency="EUR", airline="Iberia")

    async def fake_quote(from_currency, to_currency, amount_minor, auth_header):
        assert from_currency == "EUR"
        assert to_currency == "RON"
        assert amount_minor == 16482
        return {"received_minor": 82000, "applied_rate": 4.9756}

    monkeypatch.setattr("app.tools.registry.duffel_client.search_cheapest_flight", fake_flight)
    monkeypatch.setattr("app.tools.registry.exchange_tools.get_quote", fake_quote)

    result = await execute_tool("estimate_trip_cost", _TRIP_ARGS, "Bearer token", ToolResultCache())

    assert result["available"] is True
    assert result["total_estimate_minor"] == 82000
    assert result["flight"]["applied_exchange_rate"] == 4.9756


async def test_estimate_trip_cost_conversion_failure_marks_unavailable(monkeypatch):
    monkeypatch.setattr("app.tools.registry.settings.duffel_access_token", "token")

    async def fake_flight(**kwargs):
        return FlightEstimate(price_minor=16482, currency="EUR", airline="Iberia")

    async def fake_quote(*args, **kwargs):
        raise ToolError("exchange-service indisponibil")

    monkeypatch.setattr("app.tools.registry.duffel_client.search_cheapest_flight", fake_flight)
    monkeypatch.setattr("app.tools.registry.exchange_tools.get_quote", fake_quote)

    result = await execute_tool("estimate_trip_cost", _TRIP_ARGS, "Bearer token", ToolResultCache())

    assert result["available"] is False


async def test_estimate_trip_cost_missing_required_field():
    with pytest.raises(ToolError):
        await execute_tool(
            "estimate_trip_cost",
            {"destination_city": "Barcelona"},
            "Bearer token",
            ToolResultCache(),
        )


async def test_estimate_trip_cost_defaults_travelers_to_one(monkeypatch):
    monkeypatch.setattr("app.tools.registry.settings.duffel_access_token", "token")

    captured = {}

    async def fake_flight(**kwargs):
        captured["adults"] = kwargs["adults"]
        return None

    monkeypatch.setattr("app.tools.registry.duffel_client.search_cheapest_flight", fake_flight)

    await execute_tool("estimate_trip_cost", _TRIP_ARGS, "Bearer token", ToolResultCache())

    assert captured["adults"] == 1


# --- propose_create_savings_pocket ---------------------------------------


async def test_propose_create_savings_pocket_sets_pending_action():
    cache = ToolResultCache()
    result = await execute_tool(
        "propose_create_savings_pocket", {"name": "Vacanță Barcelona", "target_ron": 3500}, "Bearer token", cache
    )

    assert result["requires_confirmation"] is True
    assert cache.pending_action["type"] == "create_pocket"
    assert cache.pending_action["payload"] == {"name": "Vacanță Barcelona", "target_minor": 350000}


async def test_propose_create_savings_pocket_missing_fields():
    with pytest.raises(ToolError):
        await execute_tool("propose_create_savings_pocket", {"name": "X"}, "Bearer token", ToolResultCache())
