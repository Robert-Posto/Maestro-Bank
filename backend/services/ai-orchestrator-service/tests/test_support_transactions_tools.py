"""Teste pentru app/tools/support_transactions_tools.py — în special
period_bounds (calcul determinist de interval), sursa bug-ului raportat:
"luna trecută" întorcea și tranzacții din luna curentă, pentru că
modelul deducea el însuși intervalul dintr-o listă brută de tranzacții.
"""

from datetime import datetime, timezone

import pytest

from app.tools import support_transactions_tools as tools

# 2026-08-28, ora oarecare, UTC — data "curentă" fixă, pentru determinism.
_NOW = datetime(2026, 8, 28, 14, 30, tzinfo=timezone.utc)


def test_this_month_bounds():
    start, end = tools.period_bounds("this_month", now=_NOW)
    assert start == datetime(2026, 8, 1, tzinfo=timezone.utc)
    assert end == datetime(2026, 9, 1, tzinfo=timezone.utc)


def test_last_month_bounds_does_not_include_current_month():
    """Bug-ul raportat: "luna trecută" (iulie) întorcea și tranzacții din
    august (luna curentă). Limita de sus TREBUIE să fie exact 1 august —
    nicio tranzacție din august nu poate trece de acest filtru."""
    start, end = tools.period_bounds("last_month", now=_NOW)
    assert start == datetime(2026, 7, 1, tzinfo=timezone.utc)
    assert end == datetime(2026, 8, 1, tzinfo=timezone.utc)


def test_last_month_bounds_rolls_over_year_boundary():
    """Ianuarie -> luna trecută e decembrie anul TRECUT, nu luna 0."""
    now = datetime(2026, 1, 15, tzinfo=timezone.utc)
    start, end = tools.period_bounds("last_month", now=now)
    assert start == datetime(2025, 12, 1, tzinfo=timezone.utc)
    assert end == datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_today_bounds():
    start, end = tools.period_bounds("today", now=_NOW)
    assert start == datetime(2026, 8, 28, tzinfo=timezone.utc)
    assert end == _NOW


def test_last_7_days_bounds():
    start, end = tools.period_bounds("last_7_days", now=_NOW)
    assert (end - start).days == 7
    assert end == _NOW


def test_unknown_period_raises():
    with pytest.raises(ValueError):
        tools.period_bounds("next_century", now=_NOW)  # type: ignore[arg-type]


# --- get_transactions_by_period — parametrii trimiși mai departe la Gateway --------


async def test_get_transactions_by_period_sends_computed_bounds(monkeypatch):
    captured: dict = {}

    async def fake_gateway_request(method, path, authorization, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["params"] = kwargs.get("params")
        return [{"id": "tx1"}]

    monkeypatch.setattr(tools, "gateway_request", fake_gateway_request)
    monkeypatch.setattr(
        tools, "period_bounds", lambda period, now=None: (datetime(2026, 7, 1, tzinfo=timezone.utc), datetime(2026, 8, 1, tzinfo=timezone.utc))
    )

    result = await tools.get_transactions_by_period("Bearer x", "last_month")

    assert result == [{"id": "tx1"}]
    assert captured["path"] == "/api/transactions"
    assert captured["params"]["date_from"] == "2026-07-01T00:00:00+00:00"
    assert captured["params"]["date_to"] == "2026-08-01T00:00:00+00:00"


async def test_get_transactions_by_period_clamps_limit(monkeypatch):
    captured: dict = {}

    async def fake_gateway_request(method, path, authorization, **kwargs):
        captured["params"] = kwargs.get("params")
        return []

    monkeypatch.setattr(tools, "gateway_request", fake_gateway_request)

    await tools.get_transactions_by_period("Bearer x", "this_month", limit=9999)

    assert captured["params"]["limit"] == 100


# --- get_transactions_by_date_range — interval EXPLICIT, cerut de user cu date -----


def test_explicit_range_bounds_includes_entire_end_day():
    """Bug la care s-ar fi expus ușor: date_to = miezul nopții ar exclude
    orice tranzacție din ultima zi care nu are ora exact 00:00:00 — limita
    de sus TREBUIE să acopere toată ziua (până la 23:59:59.999999)."""
    start, end = tools._explicit_range_bounds("2026-08-15", "2026-08-20")
    assert start == datetime(2026, 8, 15, tzinfo=timezone.utc)
    assert end == datetime(2026, 8, 20, 23, 59, 59, 999999, tzinfo=timezone.utc)


def test_explicit_range_bounds_single_day():
    start, end = tools._explicit_range_bounds("2026-08-15", "2026-08-15")
    assert start == datetime(2026, 8, 15, tzinfo=timezone.utc)
    assert end == datetime(2026, 8, 15, 23, 59, 59, 999999, tzinfo=timezone.utc)


def test_explicit_range_bounds_rejects_invalid_format():
    with pytest.raises(ValueError):
        tools._explicit_range_bounds("15 august", "2026-08-20")


def test_explicit_range_bounds_rejects_inverted_range():
    with pytest.raises(ValueError):
        tools._explicit_range_bounds("2026-08-20", "2026-08-15")


async def test_get_transactions_by_date_range_sends_computed_bounds(monkeypatch):
    captured: dict = {}

    async def fake_gateway_request(method, path, authorization, **kwargs):
        captured["path"] = path
        captured["params"] = kwargs.get("params")
        return [{"id": "tx-aug-18"}]

    monkeypatch.setattr(tools, "gateway_request", fake_gateway_request)

    result = await tools.get_transactions_by_date_range("Bearer x", "2026-08-15", "2026-08-20")

    assert result == [{"id": "tx-aug-18"}]
    assert captured["path"] == "/api/transactions"
    assert captured["params"]["date_from"] == "2026-08-15T00:00:00+00:00"
    assert captured["params"]["date_to"] == "2026-08-20T23:59:59.999999+00:00"


async def test_get_transactions_by_date_range_returns_clear_error_on_bad_input(monkeypatch):
    async def fail_if_called(*args, **kwargs):
        raise AssertionError("gateway_request nu trebuia apelat pentru un interval invalid")

    monkeypatch.setattr(tools, "gateway_request", fail_if_called)

    result = await tools.get_transactions_by_date_range("Bearer x", "2026-08-20", "2026-08-15")

    assert "error" in result
