"""Teste pentru app/tools/support_account_actions_tools.py — execuția REALĂ
a acțiunilor de scriere ale Support Agent (transfer intern, setări card).

Focus special pe granița de securitate: fiecare funcție rezolvă contul/
cardul ȚINTĂ STRICT din datele proprii ale userului (get_my_accounts/
get_my_cards) — niciodată dintr-un IBAN/card_id primit direct.
"""

import pytest

from app.tools import support_account_actions_tools as tools

pytestmark = pytest.mark.asyncio


# --- execute_internal_transfer -----------------------------------------------


async def test_internal_transfer_rejects_invalid_account_type(monkeypatch):
    async def fail_if_called(*args, **kwargs):
        raise AssertionError("gateway_request nu trebuia apelat pentru un tip de cont invalid")

    monkeypatch.setattr(tools, "gateway_request", fail_if_called)

    result = await tools.execute_internal_transfer("Bearer x", "current", 100)

    assert result["error"]
    assert result["status_code"] == 422


async def test_internal_transfer_rejects_negative_amount(monkeypatch):
    async def fail_if_called(*args, **kwargs):
        raise AssertionError("gateway_request nu trebuia apelat pentru o sumă invalidă")

    monkeypatch.setattr(tools, "gateway_request", fail_if_called)

    result = await tools.execute_internal_transfer("Bearer x", "savings", -50)

    assert result["error"]
    assert result["status_code"] == 422


async def test_internal_transfer_fails_clearly_when_account_not_owned(monkeypatch):
    """Userul nu are un cont "savings" deschis — eroare clară, NU o
    presupunere/inventare de IBAN."""

    async def fake_get_my_accounts(authorization):
        return [{"account_type": "current", "iban": "RO00CURRENT"}]

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("gateway_request nu trebuia apelat — contul țintă nu există")

    monkeypatch.setattr(tools, "get_my_accounts", fake_get_my_accounts)
    monkeypatch.setattr(tools, "gateway_request", fail_if_called)

    result = await tools.execute_internal_transfer("Bearer x", "savings", 100)

    assert result["error"]
    assert result["status_code"] == 404


async def test_internal_transfer_resolves_iban_strictly_from_own_accounts(monkeypatch):
    """Destinația (`to_iban`) vine STRICT din contul PROPRIU al userului,
    găsit după `account_type` — niciodată dintr-un IBAN primit ca parametru
    (tool-ul nici măcar nu are un asemenea parametru)."""

    async def fake_get_my_accounts(authorization):
        return [
            {"account_type": "current", "iban": "RO00CURRENT"},
            {"account_type": "savings", "iban": "RO00SAVINGS"},
        ]

    captured: dict = {}

    async def fake_gateway_request(method, path, authorization, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["json"] = kwargs.get("json")
        return {"id": "TX-1", "amount_minor": 50000}

    monkeypatch.setattr(tools, "get_my_accounts", fake_get_my_accounts)
    monkeypatch.setattr(tools, "gateway_request", fake_gateway_request)

    result = await tools.execute_internal_transfer("Bearer x", "savings", 500)

    assert result["to_account_type"] == "savings"
    assert result["transfer"]["id"] == "TX-1"
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/transactions/transfers"
    assert captured["json"]["to_iban"] == "RO00SAVINGS"
    assert captured["json"]["amount_minor"] == 50000


async def test_internal_transfer_propagates_gateway_error(monkeypatch):
    async def fake_get_my_accounts(authorization):
        return [{"account_type": "savings", "iban": "RO00SAVINGS"}]

    async def fake_gateway_request(method, path, authorization, **kwargs):
        from app.tools._gateway_client import GatewayError

        raise GatewayError(409, "Sold insuficient.")

    monkeypatch.setattr(tools, "get_my_accounts", fake_get_my_accounts)
    monkeypatch.setattr(tools, "gateway_request", fake_gateway_request)

    result = await tools.execute_internal_transfer("Bearer x", "savings", 500)

    assert result["error"] == "Sold insuficient."
    assert result["status_code"] == 409


# --- execute_update_card_settings --------------------------------------------


async def test_update_card_settings_resolves_card_by_last_four(monkeypatch):
    async def fake_get_my_cards(authorization):
        return [{"id": "card-1", "last_four": "1111"}, {"id": "card-2", "last_four": "2222"}]

    captured: dict = {}

    async def fake_gateway_request(method, path, authorization, **kwargs):
        captured["path"] = path
        return {"id": "card-2", "is_frozen": True}

    monkeypatch.setattr(tools, "get_my_cards", fake_get_my_cards)
    monkeypatch.setattr(tools, "gateway_request", fake_gateway_request)

    result = await tools.execute_update_card_settings("Bearer x", last_four="2222", freeze=True)

    assert result["card"]["id"] == "card-2"
    assert captured["path"] == "/api/accounts/cards/card-2/freeze"


async def test_update_card_settings_unknown_last_four_returns_error(monkeypatch):
    async def fake_get_my_cards(authorization):
        return [{"id": "card-1", "last_four": "1111"}]

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("gateway_request nu trebuia apelat pentru un card inexistent")

    monkeypatch.setattr(tools, "get_my_cards", fake_get_my_cards)
    monkeypatch.setattr(tools, "gateway_request", fail_if_called)

    result = await tools.execute_update_card_settings("Bearer x", last_four="9999", freeze=True)

    assert result["error"]
    assert result["status_code"] == 404


async def test_update_card_settings_applies_multiple_fields_in_one_call(monkeypatch):
    async def fake_get_my_cards(authorization):
        return [{"id": "card-1", "last_four": "1111"}]

    calls: list[tuple[str, str, dict | None]] = []

    async def fake_gateway_request(method, path, authorization, **kwargs):
        calls.append((method, path, kwargs.get("json")))
        return {"id": "card-1"}

    monkeypatch.setattr(tools, "get_my_cards", fake_get_my_cards)
    monkeypatch.setattr(tools, "gateway_request", fake_gateway_request)

    result = await tools.execute_update_card_settings(
        "Bearer x", international_payments_enabled=False, daily_limit=500
    )

    assert "card" in result
    paths = [c[1] for c in calls]
    assert "/api/accounts/cards/card-1/settings" in paths
    assert "/api/accounts/cards/card-1/limits" in paths
    settings_call = next(c for c in calls if c[1].endswith("/settings"))
    assert settings_call[2] == {"international_payments_enabled": False}
    limits_call = next(c for c in calls if c[1].endswith("/limits"))
    assert limits_call[2] == {"daily_limit_minor": 50000}


async def test_update_card_settings_rejects_non_positive_daily_limit(monkeypatch):
    async def fake_get_my_cards(authorization):
        return [{"id": "card-1", "last_four": "1111"}]

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("gateway_request nu trebuia apelat pentru o limită invalidă")

    monkeypatch.setattr(tools, "get_my_cards", fake_get_my_cards)
    monkeypatch.setattr(tools, "gateway_request", fail_if_called)

    result = await tools.execute_update_card_settings("Bearer x", daily_limit=0)

    assert result["error"]
    assert result["status_code"] == 422


async def test_update_card_settings_no_fields_returns_error(monkeypatch):
    async def fake_get_my_cards(authorization):
        return [{"id": "card-1", "last_four": "1111"}]

    monkeypatch.setattr(tools, "get_my_cards", fake_get_my_cards)

    result = await tools.execute_update_card_settings("Bearer x")

    assert result["error"]
    assert result["status_code"] == 422


# --- execute_open_account -----------------------------------------------


async def test_open_account_rejects_invalid_type(monkeypatch):
    async def fail_if_called(*args, **kwargs):
        raise AssertionError("gateway_request nu trebuia apelat pentru un tip de cont invalid")

    monkeypatch.setattr(tools, "gateway_request", fail_if_called)

    result = await tools.execute_open_account("Bearer x", "current")

    assert result["error"]
    assert result["status_code"] == 422


async def test_open_account_rejects_student_type():
    # Studentul necesită un document justificativ, pe care agentul nu-l poate atașa.
    result = await tools.execute_open_account("Bearer x", "student")

    assert result["error"]
    assert result["status_code"] == 422


async def test_open_account_calls_gateway_with_normalized_type(monkeypatch):
    captured: dict = {}

    async def fake_gateway_request(method, path, authorization, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["json"] = kwargs.get("json")
        return {"id": "acc-2", "account_type": "eur", "iban": "RO00EUR"}

    monkeypatch.setattr(tools, "gateway_request", fake_gateway_request)

    result = await tools.execute_open_account("Bearer x", "EUR")

    assert result["account"]["account_type"] == "eur"
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/accounts/new"
    assert captured["json"] == {"account_type": "eur"}


async def test_open_account_propagates_gateway_error(monkeypatch):
    async def fake_gateway_request(method, path, authorization, **kwargs):
        from app.tools._gateway_client import GatewayError

        raise GatewayError(409, 'Ai deja un cont de tip "savings".')

    monkeypatch.setattr(tools, "gateway_request", fake_gateway_request)

    result = await tools.execute_open_account("Bearer x", "savings")

    assert result["error"] == 'Ai deja un cont de tip "savings".'
    assert result["status_code"] == 409


# --- execute_currency_exchange -------------------------------------------


async def test_currency_exchange_rejects_invalid_currency(monkeypatch):
    async def fail_if_called(*args, **kwargs):
        raise AssertionError("gateway_request nu trebuia apelat pentru o valută invalidă")

    monkeypatch.setattr(tools, "gateway_request", fail_if_called)

    result = await tools.execute_currency_exchange("Bearer x", "RON", "XYZ", 100)

    assert result["error"]
    assert result["status_code"] == 422


async def test_currency_exchange_rejects_same_currency(monkeypatch):
    async def fail_if_called(*args, **kwargs):
        raise AssertionError("gateway_request nu trebuia apelat pentru aceeași valută")

    monkeypatch.setattr(tools, "gateway_request", fail_if_called)

    result = await tools.execute_currency_exchange("Bearer x", "RON", "ron", 100)

    assert result["error"]
    assert result["status_code"] == 422


async def test_currency_exchange_rejects_non_positive_amount(monkeypatch):
    async def fail_if_called(*args, **kwargs):
        raise AssertionError("gateway_request nu trebuia apelat pentru o sumă invalidă")

    monkeypatch.setattr(tools, "gateway_request", fail_if_called)

    result = await tools.execute_currency_exchange("Bearer x", "RON", "EUR", 0)

    assert result["error"]
    assert result["status_code"] == 422


async def test_currency_exchange_calls_gateway_with_minor_amount(monkeypatch):
    captured: dict = {}

    async def fake_gateway_request(method, path, authorization, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["json"] = kwargs.get("json")
        return {"id": "ex-1", "from_currency": "RON", "to_currency": "EUR", "received_minor": 2000}

    monkeypatch.setattr(tools, "gateway_request", fake_gateway_request)

    result = await tools.execute_currency_exchange("Bearer x", "ron", "eur", 100)

    assert result["exchange"]["id"] == "ex-1"
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/exchange/execute"
    assert captured["json"] == {"from_currency": "RON", "to_currency": "EUR", "amount_minor": 10000}


async def test_currency_exchange_propagates_gateway_error(monkeypatch):
    async def fake_gateway_request(method, path, authorization, **kwargs):
        from app.tools._gateway_client import GatewayError

        raise GatewayError(400, "Nu ai încă un cont în EUR.")

    monkeypatch.setattr(tools, "gateway_request", fake_gateway_request)

    result = await tools.execute_currency_exchange("Bearer x", "RON", "EUR", 100)

    assert result["error"] == "Nu ai încă un cont în EUR."
    assert result["status_code"] == 400
