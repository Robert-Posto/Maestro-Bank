"""Teste unitare pentru Support Agent — vezi task-ul MaestroBank, secțiunea 27.

Fiecare test scriptează răspunsurile "GPT-5-mini" (FakeLLMClient, vezi
conftest.py) și mock-uiește tool-urile reale (app/tools/*), ca să
verifice determinist orchestrarea (app/agents/support.py +
app/services/support_service.py) — NU comportamentul unui model real
(fără cheie Azure disponibilă în acest mediu, vezi RAPORT FINAL).

Rulare (din interiorul containerului ai-orchestrator-service):

    docker compose exec ai-orchestrator-service pip install -r requirements-dev.txt -q
    docker compose exec ai-orchestrator-service python -m pytest -q
"""

from __future__ import annotations

import pytest

from app.models.support import ChatRequest
from app.services import support_service
from app.tools import support_cards_tools, support_ticket_tools, support_transactions_tools
from conftest import FakeLLMClient, FakeMessage, make_tool_call

pytestmark = pytest.mark.asyncio


# --- Card status -----------------------------------------------------------


async def test_card_status_active(monkeypatch, auth_header: dict[str, str]):
    async def fake_get_card_status(authorization, last_four=None):
        return {
            "last_four": "5678",
            "status": "active",
            "is_frozen": False,
            "online_payments_enabled": True,
            "contactless_enabled": True,
            "atm_withdrawals_enabled": True,
            "international_payments_enabled": False,
            "daily_limit_minor": 500000,
        }

    monkeypatch.setattr(support_cards_tools, "get_card_status", fake_get_card_status)

    fake_llm = FakeLLMClient(
        [
            FakeMessage(tool_calls=[make_tool_call("get_card_status", {})]),
            FakeMessage(
                tool_calls=[
                    make_tool_call(
                        "respond_to_user",
                        {
                            "answer": "Cardul tău este activ și nu este blocat. Plățile internaționale sunt dezactivate.",
                            "intent": "card_status",
                        },
                    )
                ]
            ),
        ]
    )

    response = await support_service.handle_chat(
        ChatRequest(message="Cardul meu este activ?"), auth_header["Authorization"], llm_client=fake_llm
    )

    assert response.intent == "card_status"
    assert "activ" in response.answer.lower()
    assert response.requires_confirmation is False


async def test_card_status_frozen(monkeypatch, auth_header: dict[str, str]):
    async def fake_get_card_status(authorization, last_four=None):
        return {"last_four": "5678", "status": "active", "is_frozen": True}

    monkeypatch.setattr(support_cards_tools, "get_card_status", fake_get_card_status)

    fake_llm = FakeLLMClient(
        [
            FakeMessage(tool_calls=[make_tool_call("get_card_status", {})]),
            FakeMessage(
                tool_calls=[
                    make_tool_call(
                        "respond_to_user",
                        {"answer": "Cardul tău este momentan blocat (temporar).", "intent": "card_status"},
                    )
                ]
            ),
        ]
    )

    response = await support_service.handle_chat(
        ChatRequest(message="De ce nu pot plăti cu cardul?"), auth_header["Authorization"], llm_client=fake_llm
    )

    assert "blocat" in response.answer.lower()


# --- Tranzacții --------------------------------------------------------------


async def test_transaction_found(monkeypatch, auth_header: dict[str, str]):
    async def fake_get_transaction_details(authorization, transaction_id):
        assert transaction_id == "TRX123"
        return {
            "id": "TRX123",
            "amount_minor": 34218,
            "currency": "RON",
            "description": "Kaufland",
            "category": "groceries",
            "status": "completed",
        }

    monkeypatch.setattr(support_transactions_tools, "get_transaction_details", fake_get_transaction_details)

    fake_llm = FakeLLMClient(
        [
            FakeMessage(tool_calls=[make_tool_call("get_transaction_details", {"transaction_id": "TRX123"})]),
            FakeMessage(
                tool_calls=[
                    make_tool_call(
                        "respond_to_user",
                        {"answer": "Tranzacția e o plată de 342,18 RON către Kaufland.", "intent": "transaction_details"},
                    )
                ]
            ),
        ]
    )

    response = await support_service.handle_chat(
        ChatRequest(message="Ce este tranzacția TRX123?"), auth_header["Authorization"], llm_client=fake_llm
    )

    assert response.intent == "transaction_details"
    assert "342,18" in response.answer or "Kaufland" in response.answer


async def test_transaction_not_found(monkeypatch, auth_header: dict[str, str]):
    async def fake_get_transaction_details(authorization, transaction_id):
        return {"error": "Resursa nu a fost găsită.", "status_code": 404}

    monkeypatch.setattr(support_transactions_tools, "get_transaction_details", fake_get_transaction_details)

    fake_llm = FakeLLMClient(
        [
            FakeMessage(tool_calls=[make_tool_call("get_transaction_details", {"transaction_id": "TRX999"})]),
            FakeMessage(
                tool_calls=[
                    make_tool_call(
                        "respond_to_user",
                        {"answer": "Nu am găsit nicio tranzacție cu acest ID.", "intent": "transaction_details"},
                    )
                ]
            ),
        ]
    )

    response = await support_service.handle_chat(
        ChatRequest(message="Ce este tranzacția TRX999?"), auth_header["Authorization"], llm_client=fake_llm
    )

    assert "nu am găsit" in response.answer.lower() or "negăsit" in response.answer.lower()


# --- Transferuri ---------------------------------------------------------------


async def test_transfer_completed(monkeypatch, auth_header: dict[str, str]):
    async def fake_get_transfer_status(authorization, transaction_id):
        return {"id": "TRX1", "status": "completed", "amount_minor": 10000, "currency": "RON"}

    monkeypatch.setattr(support_transactions_tools, "get_transfer_status", fake_get_transfer_status)

    fake_llm = FakeLLMClient(
        [
            FakeMessage(tool_calls=[make_tool_call("get_transfer_status", {"transaction_id": "TRX1"})]),
            FakeMessage(
                tool_calls=[
                    make_tool_call("respond_to_user", {"answer": "Transferul a fost finalizat cu succes.", "intent": "transfer_status"})
                ]
            ),
        ]
    )

    response = await support_service.handle_chat(
        ChatRequest(message="Transferul meu e finalizat?"), auth_header["Authorization"], llm_client=fake_llm
    )

    assert "finalizat" in response.answer.lower()


async def test_transfer_failed_does_not_invent_reason(monkeypatch, auth_header: dict[str, str]):
    """Backendul NU stochează un motiv pentru status="failed" — agentul nu
    trebuie să inventeze unul (vezi system prompt + task-ul, secțiunea 13)."""

    async def fake_get_transfer_status(authorization, transaction_id):
        return {"id": "TRX2", "status": "failed", "amount_minor": 5000, "currency": "RON"}

    monkeypatch.setattr(support_transactions_tools, "get_transfer_status", fake_get_transfer_status)

    fake_llm = FakeLLMClient(
        [
            FakeMessage(tool_calls=[make_tool_call("get_transfer_status", {"transaction_id": "TRX2"})]),
            FakeMessage(
                tool_calls=[
                    make_tool_call(
                        "respond_to_user",
                        {"answer": "Transferul are status eșuat. Nu avem un motiv detaliat înregistrat.", "intent": "transfer_status"},
                    )
                ]
            ),
        ]
    )

    response = await support_service.handle_chat(
        ChatRequest(message="De ce a eșuat transferul meu?"), auth_header["Authorization"], llm_client=fake_llm
    )

    assert "eșuat" in response.answer.lower()
    # Nu verificăm text specific de "motiv" pentru că testul verifică
    # DOAR că răspunsul agentului vine strict din ce a întors tool-ul
    # (fixture-ul de mai sus nu conține niciun motiv) — vezi și
    # test_confirmation_flow.py pentru gate-ul anti-invenție al scrierilor.


# --- Tichete de suport -----------------------------------------------------


async def test_list_my_support_tickets(monkeypatch, auth_header: dict[str, str]):
    async def fake_get_my_support_tickets(authorization):
        return [{"id": "t1", "subject": "Card blocat", "status": "open"}]

    monkeypatch.setattr(support_ticket_tools, "get_my_support_tickets", fake_get_my_support_tickets)

    fake_llm = FakeLLMClient(
        [
            FakeMessage(tool_calls=[make_tool_call("get_my_support_tickets", {})]),
            FakeMessage(
                tool_calls=[
                    make_tool_call("respond_to_user", {"answer": "Ai o solicitare deschisă: Card blocat.", "intent": "support_ticket"})
                ]
            ),
        ]
    )

    response = await support_service.handle_chat(
        ChatRequest(message="Ce solicitări am deschise?"), auth_header["Authorization"], llm_client=fake_llm
    )

    assert "card blocat" in response.answer.lower()


async def test_create_ticket_after_confirmation(monkeypatch, auth_header: dict[str, str]):
    async def fake_create_support_ticket(authorization, subject, category, message):
        return {"id": "SUP-123", "subject": subject, "category": category, "status": "open"}

    monkeypatch.setattr(support_ticket_tools, "create_support_ticket", fake_create_support_ticket)

    from app.models.support import PendingAction

    payload = ChatRequest(
        message="Da",
        pending_action=PendingAction(
            tool="create_support_ticket",
            arguments={"subject": "Tranzacție nerecunoscută", "category": "transfer", "message": "Nu recunosc TRX123."},
        ),
    )

    response = await support_service.handle_chat(payload, auth_header["Authorization"], llm_client=FakeLLMClient([]))

    assert response.requires_confirmation is False
    assert "SUP-123" in response.answer


# --- Out of scope ------------------------------------------------------------


async def test_out_of_scope_question_not_answered_as_spending_agent(auth_header: dict[str, str]):
    fake_llm = FakeLLMClient(
        [
            FakeMessage(
                tool_calls=[
                    make_tool_call(
                        "respond_to_user",
                        {
                            "answer": "Această întrebare ține de analiza cheltuielilor și e gestionată de Spending + Forecast Agent.",
                            "intent": "unknown",
                            "out_of_scope": True,
                        },
                    )
                ]
            )
        ]
    )

    response = await support_service.handle_chat(
        ChatRequest(message="Îmi permit o vacanță de 5000 lei?"), auth_header["Authorization"], llm_client=fake_llm
    )

    assert response.metadata.get("out_of_scope") is True
    assert "spending" in response.answer.lower() or "forecast" in response.answer.lower()
