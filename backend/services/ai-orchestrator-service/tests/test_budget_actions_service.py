"""Teste pentru app/services/budget_actions_service.py — logica de
PROPUNERE (nu execuție) pentru creare/modificare/ștergere buget, plus
execuția reală (mock-uită) declanșată de confirmare.
"""

import pytest

from app.services import budget_actions_service
from app.tools.errors import ToolError

# NOTĂ: fără `pytestmark = pytest.mark.asyncio` — pytest.ini are deja
# `asyncio_mode = auto`; testele async de mai jos rulează corect oricum,
# iar un mark explicit la nivel de modul ar afecta greșit testele sincrone.


def _budget(id_: str, name: str, category: str, limit_minor: int, active: bool = True) -> dict:
    return {"id": id_, "name": name, "category": category, "limit_minor": limit_minor, "active": active}


# --- find_budget -----------------------------------------------------------


def test_find_budget_by_exact_name():
    budgets = [_budget("b1", "Restaurante", "restaurants", 90000)]
    assert budget_actions_service.find_budget(budgets, "Restaurante")["id"] == "b1"


def test_find_budget_by_category_case_insensitive():
    budgets = [_budget("b1", "Restaurante", "restaurants", 90000)]
    assert budget_actions_service.find_budget(budgets, "RESTAURANTS")["id"] == "b1"


def test_find_budget_no_match_returns_none():
    budgets = [_budget("b1", "Restaurante", "restaurants", 90000)]
    assert budget_actions_service.find_budget(budgets, "shopping") is None


def test_find_budget_ambiguous_returns_none():
    budgets = [
        _budget("b1", "Shopping", "shopping", 50000),
        _budget("b2", "Shopping extra", "shopping", 30000),
    ]
    # ambele au category "shopping" -> query "shopping" ar potrivi 2, nu 1
    assert budget_actions_service.find_budget(budgets, "shopping") is None


def test_find_budget_ignores_inactive():
    budgets = [_budget("b1", "Vechi", "other", 10000, active=False)]
    assert budget_actions_service.find_budget(budgets, "Vechi") is None


# --- propose_create ----------------------------------------------------------


def test_propose_create_valid():
    action = budget_actions_service.propose_create("restaurants", 80000, None, existing_budgets=[])
    assert action["type"] == "create_budget"
    assert action["payload"] == {"name": "Restaurants", "category": "restaurants", "limit_minor": 80000, "period": "monthly"}
    assert "800,00 lei" in action["summary"]


def test_propose_create_uses_custom_name():
    action = budget_actions_service.propose_create("shopping", 100000, "Haine de iarnă", existing_budgets=[])
    assert action["payload"]["name"] == "Haine de iarnă"


def test_propose_create_rejects_invalid_category():
    with pytest.raises(ToolError):
        budget_actions_service.propose_create("altceva", 10000, None, existing_budgets=[])


def test_propose_create_rejects_non_positive_amount():
    with pytest.raises(ToolError):
        budget_actions_service.propose_create("shopping", 0, None, existing_budgets=[])


def test_propose_create_rejects_duplicate_active_category():
    existing = [_budget("b1", "Shopping", "shopping", 50000)]
    with pytest.raises(ToolError):
        budget_actions_service.propose_create("shopping", 100000, None, existing_budgets=existing)


def test_propose_create_allows_category_if_existing_is_inactive():
    existing = [_budget("b1", "Shopping vechi", "shopping", 50000, active=False)]
    action = budget_actions_service.propose_create("shopping", 100000, None, existing_budgets=existing)
    assert action["type"] == "create_budget"


# --- propose_update ----------------------------------------------------------


def test_propose_update_valid():
    existing = [_budget("b1", "Shopping", "shopping", 50000)]
    action = budget_actions_service.propose_update("shopping", 150000, existing_budgets=existing)
    assert action["type"] == "update_budget"
    assert action["payload"] == {"budget_id": "b1", "limit_minor": 150000}


def test_propose_update_target_not_found():
    with pytest.raises(ToolError):
        budget_actions_service.propose_update("inexistent", 100000, existing_budgets=[])


def test_propose_update_rejects_non_positive_amount():
    existing = [_budget("b1", "Shopping", "shopping", 50000)]
    with pytest.raises(ToolError):
        budget_actions_service.propose_update("shopping", -100, existing_budgets=existing)


# --- propose_delete ----------------------------------------------------------


def test_propose_delete_valid():
    existing = [_budget("b1", "Entertainment", "entertainment", 40000)]
    action = budget_actions_service.propose_delete("entertainment", existing_budgets=existing)
    assert action["type"] == "delete_budget"
    assert action["payload"] == {"budget_id": "b1"}


def test_propose_delete_target_not_found():
    with pytest.raises(ToolError):
        budget_actions_service.propose_delete("inexistent", existing_budgets=[])


# --- execute_confirmed_action (mock-uit) --------------------------------------


async def test_execute_confirmed_action_create(monkeypatch):
    async def fake_create(payload, auth_header):
        return {"id": "b1", "name": payload["name"], "category": payload["category"], "limit_minor": payload["limit_minor"]}

    monkeypatch.setattr("app.tools.budgets_tools.create_budget", fake_create)

    result = await budget_actions_service.execute_confirmed_action(
        "create_budget", {"name": "Restaurante", "category": "restaurants", "limit_minor": 80000}, "Bearer token"
    )

    assert result["success"] is True
    assert result["budget"]["name"] == "Restaurante"


async def test_execute_confirmed_action_create_missing_fields():
    with pytest.raises(ToolError):
        await budget_actions_service.execute_confirmed_action("create_budget", {"name": "X"}, "Bearer token")


async def test_execute_confirmed_action_update(monkeypatch):
    async def fake_update(budget_id, fields, auth_header):
        assert budget_id == "b1"
        assert fields == {"limit_minor": 150000}
        return {"id": "b1", "name": "Shopping", "limit_minor": 150000}

    monkeypatch.setattr("app.tools.budgets_tools.update_budget", fake_update)

    result = await budget_actions_service.execute_confirmed_action(
        "update_budget", {"budget_id": "b1", "limit_minor": 150000}, "Bearer token"
    )
    assert result["success"] is True


async def test_execute_confirmed_action_update_missing_id():
    with pytest.raises(ToolError):
        await budget_actions_service.execute_confirmed_action("update_budget", {"limit_minor": 1000}, "Bearer token")


async def test_execute_confirmed_action_delete(monkeypatch):
    called = {}

    async def fake_delete(budget_id, auth_header):
        called["budget_id"] = budget_id

    monkeypatch.setattr("app.tools.budgets_tools.delete_budget", fake_delete)

    result = await budget_actions_service.execute_confirmed_action("delete_budget", {"budget_id": "b1"}, "Bearer token")

    assert result["success"] is True
    assert called["budget_id"] == "b1"


async def test_execute_confirmed_action_unknown_type():
    with pytest.raises(ToolError):
        await budget_actions_service.execute_confirmed_action("freeze_card", {}, "Bearer token")
