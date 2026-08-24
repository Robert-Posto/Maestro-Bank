"""Teste pentru fluxul de confirmare a acțiunilor de SCRIERE — vezi
task-ul MaestroBank, secțiunea 29.

`create_support_ticket` este singurul tool de scriere din V1 (freeze/unfreeze
card sunt guidance-only în această versiune — vezi RAPORT FINAL, limitări).

Rulare (din interiorul containerului ai-orchestrator-service):

    docker compose exec ai-orchestrator-service pip install -r requirements-dev.txt -q
    docker compose exec ai-orchestrator-service python -m pytest -q
"""

from __future__ import annotations

import pytest

from app.models.support import ChatRequest, PendingAction
from app.services import support_service
from app.tools import support_ticket_tools
from conftest import FakeLLMClient, FakeMessage, make_tool_call

pytestmark = pytest.mark.asyncio


async def test_write_tool_request_asks_confirmation_without_executing(monkeypatch, auth_header: dict[str, str]):
    """"Vreau să raportez o plată..." -> modelul cere create_support_ticket
    -> orchestratorul NU execută nimic, doar întoarce o întrebare de
    confirmare + pending_action. Tool-ul real de creare NU trebuie apelat."""
    called = False

    async def spy_create_support_ticket(*args, **kwargs):
        nonlocal called
        called = True
        return {"id": "SHOULD-NOT-HAPPEN"}

    monkeypatch.setattr(support_ticket_tools, "create_support_ticket", spy_create_support_ticket)

    fake_llm = FakeLLMClient(
        [
            FakeMessage(
                tool_calls=[
                    make_tool_call(
                        "create_support_ticket",
                        {
                            "subject": "Plată nerecunoscută",
                            "category": "transfer",
                            "message": "Nu recunosc o plată de 342,18 RON către Kaufland.",
                        },
                    )
                ]
            )
        ]
    )

    response = await support_service.handle_chat(
        ChatRequest(message="Vreau să raportez o plată pe care nu o recunosc."),
        auth_header["Authorization"],
        llm_client=fake_llm,
    )

    assert called is False
    assert response.requires_confirmation is True
    assert response.metadata["pending_action"]["tool"] == "create_support_ticket"
    assert "confirm" in response.answer.lower() or "da" in response.answer.lower()


async def test_explicit_yes_after_confirmation_executes_the_tool(monkeypatch, auth_header: dict[str, str]):
    called_with: dict = {}

    async def fake_create_support_ticket(authorization, subject, category, message):
        called_with.update(subject=subject, category=category, message=message)
        return {"id": "SUP-42", "status": "open"}

    monkeypatch.setattr(support_ticket_tools, "create_support_ticket", fake_create_support_ticket)

    pending = PendingAction(
        tool="create_support_ticket",
        arguments={"subject": "Plată nerecunoscută", "category": "transfer", "message": "Nu recunosc plata."},
    )

    response = await support_service.handle_chat(
        ChatRequest(message="Da, te rog.", pending_action=pending),
        auth_header["Authorization"],
        llm_client=FakeLLMClient([]),
    )

    assert called_with["subject"] == "Plată nerecunoscută"
    assert response.requires_confirmation is False
    assert "SUP-42" in response.answer


async def test_vague_intent_does_not_execute_write_action(monkeypatch, auth_header: dict[str, str]):
    """"Poate ar trebui să..." NU este o confirmare explicită — vezi
    task-ul, secțiunea 29: acest mesaj NU trebuie să declanșeze crearea
    tichetului, chiar dacă există un pending_action din turul anterior."""
    called = False

    async def spy_create_support_ticket(*args, **kwargs):
        nonlocal called
        called = True
        return {"id": "SHOULD-NOT-HAPPEN"}

    monkeypatch.setattr(support_ticket_tools, "create_support_ticket", spy_create_support_ticket)

    pending = PendingAction(
        tool="create_support_ticket",
        arguments={"subject": "Plată nerecunoscută", "category": "transfer", "message": "Nu recunosc plata."},
    )

    # Mesajul curent NU e o confirmare -> cade pe fluxul normal LLM, care
    # aici răspunde direct (fără alt tool call).
    fake_llm = FakeLLMClient(
        [FakeMessage(tool_calls=[make_tool_call("respond_to_user", {"answer": "Sigur, spune-mi cum te pot ajuta.", "intent": "unknown"})])]
    )

    response = await support_service.handle_chat(
        ChatRequest(message="Poate ar trebui să fac ceva în privința asta.", pending_action=pending),
        auth_header["Authorization"],
        llm_client=fake_llm,
    )

    assert called is False
    assert response.requires_confirmation is False


async def test_card_freeze_is_guidance_only_no_action_executed(auth_header: dict[str, str]):
    """Blocarea cardului e guidance-only în V1 (vezi task-ul, secțiunea 10 —
    permis explicit când confirmarea ar complica prea mult branch-ul).
    Nu există niciun tool `freeze_card` expus modelului — verificăm doar
    că un răspuns de ghidare nu declanșează vreo acțiune de scriere."""
    fake_llm = FakeLLMClient(
        [
            FakeMessage(
                tool_calls=[
                    make_tool_call(
                        "respond_to_user",
                        {
                            "answer": "Poți bloca temporar cardul din pagina Carduri, secțiunea Control card.",
                            "intent": "card_help",
                        },
                    )
                ]
            )
        ]
    )

    response = await support_service.handle_chat(
        ChatRequest(message="Blochează-mi cardul."), auth_header["Authorization"], llm_client=fake_llm
    )

    assert response.requires_confirmation is False
    assert "carduri" in response.answer.lower() or "control card" in response.answer.lower()
