"""Teste pentru app/tools/support_exchange_tools.py — conversia
determinist RON<->minor units (nu lăsată pe seama modelului) și
propagarea corectă a parametrilor către Gateway.
"""

from app.tools import support_exchange_tools as tools


async def test_get_exchange_quote_converts_amount_to_minor_units(monkeypatch):
    captured: dict = {}

    async def fake_gateway_request(method, path, authorization, **kwargs):
        captured["path"] = path
        captured["params"] = kwargs.get("params")
        return {"received_minor": 2015, "applied_rate": 4.97, "from_currency": "RON", "to_currency": "EUR"}

    monkeypatch.setattr(tools, "gateway_request", fake_gateway_request)

    result = await tools.get_exchange_quote("Bearer x", "ron", "eur", 100)

    assert captured["path"] == "/api/exchange/quote"
    assert captured["params"] == {"from_currency": "RON", "to_currency": "EUR", "amount_minor": 10000}
    assert result["received_minor"] == 2015


async def test_get_exchange_quote_rejects_non_positive_amount(monkeypatch):
    async def fail_if_called(*args, **kwargs):
        raise AssertionError("gateway_request nu trebuia apelat pentru o sumă invalidă")

    monkeypatch.setattr(tools, "gateway_request", fail_if_called)

    result = await tools.get_exchange_quote("Bearer x", "RON", "EUR", 0)

    assert "error" in result


async def test_get_exchange_quote_rounds_fractional_amounts(monkeypatch):
    captured: dict = {}

    async def fake_gateway_request(method, path, authorization, **kwargs):
        captured["params"] = kwargs.get("params")
        return {}

    monkeypatch.setattr(tools, "gateway_request", fake_gateway_request)

    await tools.get_exchange_quote("Bearer x", "RON", "EUR", 99.5)

    assert captured["params"]["amount_minor"] == 9950


async def test_get_exchange_rates_calls_rates_endpoint(monkeypatch):
    captured: dict = {}

    async def fake_gateway_request(method, path, authorization, **kwargs):
        captured["path"] = path
        return [{"currency": "EUR", "mid_rate": 4.97}]

    monkeypatch.setattr(tools, "gateway_request", fake_gateway_request)

    result = await tools.get_exchange_rates("Bearer x")

    assert captured["path"] == "/api/exchange/rates"
    assert result[0]["currency"] == "EUR"
