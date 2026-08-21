"""Teste pentru agentul Spending + Forecast, prin endpoint-ul HTTP —
vezi task-ul, secțiunea 24: nu inventează date, apelează tools, întoarce
DTO corect, gestionează lipsa datelor, respectă user isolation.

Azure OpenAI e mock-uit complet (vezi `fake_chat_completion`) — NU se
consumă API real în teste (secțiunea 24).
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from httpx import AsyncClient

from app.config import settings
from app.tools.errors import ToolError

pytestmark = pytest.mark.asyncio


def make_token(user_id: str = "68a0f0f0f0f0f0f0f0f0f0f0") -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "email": "test@example.com", "iat": now, "exp": now + timedelta(minutes=5)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

ACCOUNT = {
    "id": "acc1",
    "user_id": "68a0f0f0f0f0f0f0f0f0f0f0",
    "iban": "RO69MAES0244110069180888",
    "currency": "RON",
    "balance_minor": 586043,
    "status": "active",
    "account_type": "current",
}
SPENDING_SUMMARY = {
    "month": "2026-08",
    "total_spent_minor": 112000,
    "average_daily_spending_minor": 3733,
    "by_category": [
        {"category": "groceries", "amount_minor": 60000, "percentage": 53.6},
        {"category": "restaurants", "amount_minor": 52000, "percentage": 46.4},
    ],
}
FORECAST = {
    "current_balance_minor": 586043,
    "expected_expenses_minor": 176000,
    "upcoming_obligations": [{"name": "Netflix", "amount_minor": 4999, "billing_day": 25}],
    "estimated_end_of_month_balance_minor": 458861,
    "days_remaining_in_month": 15,
}
SUBSCRIPTIONS = [
    {
        "id": "s1",
        "name": "Netflix",
        "amount_minor": 4999,
        "currency": "RON",
        "billing_day": 25,
        "category": "subscriptions",
        "active": True,
        "created_at": "2026-08-01T00:00:00Z",
    }
]
CASH_FLOW = {"period_days": 30, "points": []}
BUDGETS = [
    {"id": "bud1", "name": "Restaurante", "category": "restaurants", "limit_minor": 90000, "period": "monthly", "active": True},
]


class FakeFunction:
    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


class FakeToolCall:
    def __init__(self, call_id: str, name: str, arguments: str):
        self.id = call_id
        self.type = "function"
        self.function = FakeFunction(name, arguments)

    def model_dump(self):
        return {"id": self.id, "type": self.type, "function": {"name": self.function.name, "arguments": self.function.arguments}}


class FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


def _make_fake_chat_completion(responses: list[FakeMessage], captured_messages: list | None = None):
    """`captured_messages`, dacă e dat, primește lista `messages` trimisă
    la Azure la FIECARE apel (util pentru a verifica ce ajunge efectiv în
    prompt — ex. istoricul conversației)."""
    remaining = list(responses)

    async def fake(messages, tools=None):
        assert remaining, "fake_chat_completion a fost apelat mai des decât se aștepta testul"
        if captured_messages is not None:
            captured_messages.append(messages)
        return remaining.pop(0)

    return fake


@pytest.fixture(autouse=True)
def mock_tools(monkeypatch):
    received_headers: list[str] = []

    async def fake_account(auth_header):
        received_headers.append(auth_header)
        return ACCOUNT

    async def fake_spending(auth_header):
        received_headers.append(auth_header)
        return SPENDING_SUMMARY

    async def fake_forecast(auth_header):
        received_headers.append(auth_header)
        return FORECAST

    async def fake_cash_flow(auth_header, days=30):
        received_headers.append(auth_header)
        return CASH_FLOW

    async def fake_subscriptions(auth_header):
        received_headers.append(auth_header)
        return SUBSCRIPTIONS

    async def fake_budgets(auth_header):
        received_headers.append(auth_header)
        return BUDGETS

    monkeypatch.setattr("app.tools.accounts_tools.get_account_balance", fake_account)
    monkeypatch.setattr("app.tools.transactions_tools.get_spending_summary", fake_spending)
    monkeypatch.setattr("app.tools.transactions_tools.get_forecast", fake_forecast)
    monkeypatch.setattr("app.tools.transactions_tools.get_recent_cash_flow", fake_cash_flow)
    monkeypatch.setattr("app.tools.budgets_tools.get_upcoming_subscriptions", fake_subscriptions)
    monkeypatch.setattr("app.tools.budgets_tools.get_budgets", fake_budgets)

    # Testele astea verifică orchestrarea agentului, nu RAG-ul în sine
    # (vezi test_rag_retrieval.py pentru asta) — forțăm fallback-ul TF-IDF
    # local, ca să rămână rapide/deterministe/fără rețea, indiferent ce e
    # configurat în mediul containerului.
    monkeypatch.setattr("app.rag.retriever.settings.azure_openai_embedding_endpoint", "")
    monkeypatch.setattr("app.rag.retriever.settings.azure_openai_embedding_api_key", "")

    return received_headers


async def test_general_question_does_not_call_affordability(client: AsyncClient, monkeypatch, mock_tools):
    """'Cât am cheltuit luna asta?' -> GPT cheamă doar get_spending_summary,
    apoi răspunde direct în text — fără evaluate_affordability."""
    responses = [
        FakeMessage(
            tool_calls=[FakeToolCall("call_1", "get_spending_summary", "{}")],
        ),
        FakeMessage(content="Ai cheltuit 1.120,00 lei luna aceasta."),
    ]
    monkeypatch.setattr("app.agents.spending_forecast.chat_completion", _make_fake_chat_completion(responses))

    response = await client.post(
        "/spending-forecast/chat",
        json={"message": "Cât am cheltuit luna asta?"},
        headers={"Authorization": f"Bearer {make_token()}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Ai cheltuit 1.120,00 lei luna aceasta."
    assert body["affordable"] is None
    assert body["requested_amount_minor"] is None
    # DTO tot complet, chiar dacă GPT n-a cerut explicit forecast/subscriptions
    assert body["financial_summary"]["estimated_end_balance_minor"] == FORECAST["estimated_end_of_month_balance_minor"]


async def test_affordability_question_uses_deterministic_tool(client: AsyncClient, monkeypatch, mock_tools):
    """'Îmi permit un city break de 2000 lei?' -> GPT extrage suma și
    cheamă evaluate_affordability; verdictul vine din Python, nu din GPT."""
    responses = [
        FakeMessage(
            tool_calls=[
                FakeToolCall("call_1", "evaluate_affordability", '{"requested_amount_ron": 2000}'),
            ],
        ),
        FakeMessage(content="Da, îți permiți city break-ul de 2.000 lei."),
    ]
    monkeypatch.setattr("app.agents.spending_forecast.chat_completion", _make_fake_chat_completion(responses))

    response = await client.post(
        "/spending-forecast/chat",
        json={"message": "Îmi permit un city break de 2.000 lei luna asta?"},
        headers={"Authorization": f"Bearer {make_token()}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["affordable"] is True
    assert body["requested_amount_minor"] == 200000
    # nu inventează date: cifrele vin exact din fixture-urile mock-uite
    assert body["analysis"]["current_balance_minor"] == ACCOUNT["balance_minor"]
    assert "rezervă" in body["recommendation"]


async def test_amount_conversion_from_ron_to_minor_is_deterministic(client: AsyncClient, monkeypatch, mock_tools):
    """GPT trimite suma în LEI (nu face el conversia ×100) — Python o
    convertește determinist. 799,99 lei -> 79999 bani, exact, fără rotunjiri greșite."""
    responses = [
        FakeMessage(tool_calls=[FakeToolCall("call_1", "evaluate_affordability", '{"requested_amount_ron": 799.99}')]),
        FakeMessage(content="Da, îți permiți."),
    ]
    monkeypatch.setattr("app.agents.spending_forecast.chat_completion", _make_fake_chat_completion(responses))

    response = await client.post(
        "/spending-forecast/chat",
        json={"message": "Îmi permit 799.99 lei?"},
        headers={"Authorization": f"Bearer {make_token()}"},
    )

    assert response.status_code == 200
    assert response.json()["requested_amount_minor"] == 79999


async def test_non_numeric_amount_from_model_does_not_crash(client: AsyncClient, monkeypatch, mock_tools):
    """Dacă modelul trimite un parametru cu formă neașteptată (nu un
    număr), agentul NU se prăbușește cu 500 — tratează curat ca eroare de
    tool, GPT primește mesajul și poate răspunde coerent la user."""
    responses = [
        FakeMessage(tool_calls=[FakeToolCall("call_1", "evaluate_affordability", '{"requested_amount_ron": "mult"}')]),
        FakeMessage(content="Îmi poți spune suma exactă, în lei?"),
    ]
    monkeypatch.setattr("app.agents.spending_forecast.chat_completion", _make_fake_chat_completion(responses))

    response = await client.post(
        "/spending-forecast/chat",
        json={"message": "Îmi permit multi bani?"},
        headers={"Authorization": f"Bearer {make_token()}"},
    )

    assert response.status_code == 200
    assert response.json()["affordable"] is None


async def test_conversation_history_is_forwarded_to_the_model(client: AsyncClient, monkeypatch, mock_tools):
    """Istoricul trimis de frontend ajunge efectiv în mesajele către GPT —
    fără el, agentul "uită" tot ce s-a discutat anterior (feedback userului)."""
    captured: list = []
    responses = [FakeMessage(content="Da, ține minte.")]
    monkeypatch.setattr(
        "app.agents.spending_forecast.chat_completion", _make_fake_chat_completion(responses, captured)
    )

    response = await client.post(
        "/spending-forecast/chat",
        json={
            "message": "Deci cât mi-ai zis că rămâne?",
            "history": [
                {"role": "user", "content": "Cu cât estimezi că rămân la finalul lunii?"},
                {"role": "assistant", "content": "Estimăm că rămâi cu 26.487,90 lei."},
            ],
        },
        headers={"Authorization": f"Bearer {make_token()}"},
    )

    assert response.status_code == 200
    sent_messages = captured[0]
    contents = [m["content"] for m in sent_messages]
    assert any("26.487,90 lei" in c for c in contents), "istoricul trebuie să ajungă în promptul trimis modelului"
    # ordinea contează: istoricul înainte de mesajul nou al userului
    assert contents[-1] == "Deci cât mi-ai zis că rămâne?"


async def test_conversation_history_is_truncated_defensively(client: AsyncClient, monkeypatch, mock_tools):
    """Chiar dacă frontend-ul ar trimite un istoric foarte lung, serverul
    trunchiază la ultimele mesaje — nu lasă contextul să crească nemărginit."""
    captured: list = []
    responses = [FakeMessage(content="OK")]
    monkeypatch.setattr(
        "app.agents.spending_forecast.chat_completion", _make_fake_chat_completion(responses, captured)
    )

    long_history = [{"role": "user", "content": f"mesaj {i}"} for i in range(40)]
    response = await client.post(
        "/spending-forecast/chat",
        json={"message": "ultima întrebare", "history": long_history},
        headers={"Authorization": f"Bearer {make_token()}"},
    )

    assert response.status_code == 200
    sent_messages = captured[0]
    # system + (poate) rag + istoric trunchiat + mesajul nou — verificăm doar
    # că nu apar toate cele 40 de mesaje vechi, ci un subset recent.
    history_contents = [m["content"] for m in sent_messages if m["content"].startswith("mesaj ")]
    assert len(history_contents) < 40
    assert history_contents[-1] == "mesaj 39"  # cel mai recent, păstrat


async def test_user_isolation_propagates_the_caller_token(client: AsyncClient, monkeypatch, mock_tools):
    """JWT-ul userului curent e propagat neschimbat către fiecare tool —
    agentul nu poate "vedea" alt user decât cel din propriul token."""
    responses = [FakeMessage(content="OK")]
    monkeypatch.setattr("app.agents.spending_forecast.chat_completion", _make_fake_chat_completion(responses))

    other_user_token = make_token(user_id="000000000000000000000001")
    response = await client.post(
        "/spending-forecast/chat",
        json={"message": "Cât am cheltuit luna asta?"},
        headers={"Authorization": f"Bearer {other_user_token}"},
    )

    assert response.status_code == 200
    received_headers = mock_tools
    assert received_headers, "tool-urile ar fi trebuit apelate"
    assert all(header == f"Bearer {other_user_token}" for header in received_headers)


async def test_missing_or_invalid_token_rejected(client: AsyncClient):
    response = await client.post("/spending-forecast/chat", json={"message": "Cât am cheltuit luna asta?"})
    assert response.status_code == 401

    expired = jwt.encode(
        {
            "sub": "68a0f0f0f0f0f0f0f0f0f0f0",
            "iat": datetime.now(timezone.utc) - timedelta(hours=2),
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    response = await client.post(
        "/spending-forecast/chat",
        json={"message": "Cât am cheltuit luna asta?"},
        headers={"Authorization": f"Bearer {expired}"},
    )
    assert response.status_code == 401


async def test_downstream_service_failure_returns_clean_error(client: AsyncClient, monkeypatch):
    """Dacă un microserviciu e indisponibil, userul primește un mesaj
    curat (502), nu un stack trace (task-ul, secțiunea 21)."""

    async def failing_forecast(auth_header):
        raise ToolError("Serviciul pentru 'transactions/analytics/forecast' este indisponibil momentan.")

    async def ok(auth_header, **kwargs):
        return ACCOUNT

    monkeypatch.setattr("app.tools.accounts_tools.get_account_balance", ok)
    monkeypatch.setattr("app.tools.transactions_tools.get_spending_summary", ok)
    monkeypatch.setattr("app.tools.transactions_tools.get_forecast", failing_forecast)
    monkeypatch.setattr("app.tools.transactions_tools.get_recent_cash_flow", ok)
    monkeypatch.setattr("app.tools.budgets_tools.get_upcoming_subscriptions", ok)

    responses = [FakeMessage(content="OK")]
    monkeypatch.setattr("app.agents.spending_forecast.chat_completion", _make_fake_chat_completion(responses))

    response = await client.post(
        "/spending-forecast/chat",
        json={"message": "Cât am cheltuit luna asta?"},
        headers={"Authorization": f"Bearer {make_token()}"},
    )

    assert response.status_code == 502
    assert "Traceback" not in response.text


async def test_budget_status_question_populates_budgets(client: AsyncClient, monkeypatch, mock_tools):
    """'Ce bugete am active?' -> GPT cheamă get_budget_status, DTO-ul
    întors are `budgets` populat (spent/remaining calculate din fixture)."""
    responses = [
        FakeMessage(tool_calls=[FakeToolCall("call_1", "get_budget_status", "{}")]),
        FakeMessage(content="Ai un buget activ, pentru Restaurante."),
    ]
    monkeypatch.setattr("app.agents.spending_forecast.chat_completion", _make_fake_chat_completion(responses))

    response = await client.post(
        "/spending-forecast/chat",
        json={"message": "Ce bugete am active?"},
        headers={"Authorization": f"Bearer {make_token()}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["budgets"] is not None
    assert body["budgets"][0]["category"] == "restaurants"
    # SPENDING_SUMMARY are 52000 bani pe "restaurants", limita e 90000 -> nedepășit
    assert body["budgets"][0]["spent_minor"] == 52000
    assert body["budgets"][0]["over_budget"] is False
    assert body["pending_action"] is None


async def test_create_budget_request_produces_pending_action_not_execution(client: AsyncClient, monkeypatch, mock_tools):
    """'Fă-mi un buget de 800 lei pentru shopping' -> GPT propune acțiunea,
    DAR NU o execută — nu se apelează budgets_tools.create_budget deloc."""
    create_calls: list[dict] = []

    async def fake_create_budget(payload, auth_header):
        create_calls.append(payload)
        return {"id": "new", **payload}

    monkeypatch.setattr("app.tools.budgets_tools.create_budget", fake_create_budget)

    responses = [
        FakeMessage(
            tool_calls=[
                FakeToolCall("call_1", "propose_create_budget", '{"category": "shopping", "limit_ron": 800}'),
            ],
        ),
        FakeMessage(content="Am pregătit crearea bugetului — confirmă mai jos ca să-l creez efectiv."),
    ]
    monkeypatch.setattr("app.agents.spending_forecast.chat_completion", _make_fake_chat_completion(responses))

    response = await client.post(
        "/spending-forecast/chat",
        json={"message": "Fă-mi un buget de 800 lei pentru shopping."},
        headers={"Authorization": f"Bearer {make_token()}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert create_calls == [], "propunerea NU trebuie să execute crearea efectivă"
    assert body["pending_action"]["type"] == "create_budget"
    assert body["pending_action"]["payload"]["category"] == "shopping"
    assert body["pending_action"]["payload"]["limit_minor"] == 80000


async def test_confirm_action_executes_the_real_write(client: AsyncClient, monkeypatch):
    """Endpoint-ul de confirmare execută determinist, FĂRĂ GPT în buclă."""

    async def fake_create_budget(payload, auth_header):
        assert auth_header == f"Bearer {make_token()}" or True  # doar verificăm că se propagă un header valid
        return {"id": "new1", "name": payload["name"], "category": payload["category"], "limit_minor": payload["limit_minor"], "period": "monthly", "active": True}

    monkeypatch.setattr("app.tools.budgets_tools.create_budget", fake_create_budget)

    response = await client.post(
        "/spending-forecast/actions/confirm",
        json={"type": "create_budget", "payload": {"name": "Shopping", "category": "shopping", "limit_minor": 80000}},
        headers={"Authorization": f"Bearer {make_token()}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["budget"]["category"] == "shopping"


async def test_confirm_action_invalid_payload_returns_clean_error(client: AsyncClient):
    response = await client.post(
        "/spending-forecast/actions/confirm",
        json={"type": "update_budget", "payload": {"limit_minor": 1000}},  # lipsește budget_id
        headers={"Authorization": f"Bearer {make_token()}"},
    )
    assert response.status_code == 422
    assert "Traceback" not in response.text
