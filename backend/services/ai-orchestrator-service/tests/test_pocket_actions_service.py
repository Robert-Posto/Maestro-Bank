"""Teste pentru app/services/pocket_actions_service.py — logica de
PROPUNERE (nu execuție) pentru crearea unui Pocket (obiectiv de
economisire), plus execuția reală (mock-uită), declanșată de confirmare,
în app/services/budget_actions_service.py::execute_confirmed_action
(același punct de execuție ca la bugete — vezi acel modul)."""

import pytest

from app.services import budget_actions_service, pocket_actions_service
from app.tools.errors import ToolError

# NOTĂ: fără `pytestmark = pytest.mark.asyncio` — pytest.ini are deja
# `asyncio_mode = auto` (vezi test_budget_actions_service.py).


# --- propose_create_pocket ---------------------------------------------------


def test_propose_create_pocket_valid():
    action = pocket_actions_service.propose_create_pocket("Vacanță Barcelona", 350000)
    assert action["type"] == "create_pocket"
    assert action["payload"] == {"name": "Vacanță Barcelona", "target_minor": 350000}
    assert "3500,00 lei" in action["summary"]


def test_propose_create_pocket_strips_name():
    action = pocket_actions_service.propose_create_pocket("  Vacanță  ", 100000)
    assert action["payload"]["name"] == "Vacanță"


def test_propose_create_pocket_rejects_empty_name():
    with pytest.raises(ToolError):
        pocket_actions_service.propose_create_pocket("   ", 100000)


def test_propose_create_pocket_rejects_name_too_long():
    with pytest.raises(ToolError):
        pocket_actions_service.propose_create_pocket("x" * 61, 100000)


def test_propose_create_pocket_rejects_non_positive_target():
    with pytest.raises(ToolError):
        pocket_actions_service.propose_create_pocket("Vacanță", 0)


# --- execute_confirmed_action("create_pocket") (mock-uit) --------------------


async def test_execute_confirmed_action_create_pocket(monkeypatch):
    async def fake_create(name, target_minor, auth_header):
        return {"id": "p1", "name": name, "target_minor": target_minor, "saved_minor": 0}

    monkeypatch.setattr("app.tools.pockets_tools.create_pocket", fake_create)

    result = await budget_actions_service.execute_confirmed_action(
        "create_pocket", {"name": "Vacanță Barcelona", "target_minor": 350000}, "Bearer token"
    )

    assert result["success"] is True
    assert result["pocket"]["name"] == "Vacanță Barcelona"
    assert result["pocket"]["target_minor"] == 350000


async def test_execute_confirmed_action_create_pocket_missing_fields():
    with pytest.raises(ToolError):
        await budget_actions_service.execute_confirmed_action("create_pocket", {"name": "X"}, "Bearer token")
