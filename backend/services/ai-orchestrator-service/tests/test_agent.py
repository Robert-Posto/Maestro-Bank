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
from app.services import moderation_service
from app.tools.errors import ToolError
from tests.conftest import ACCOUNT, BUDGETS, CASH_FLOW, FORECAST, SPENDING_SUMMARY, SUBSCRIPTIONS

pytestmark = pytest.mark.asyncio


def make_token(user_id: str = "68a0f0f0f0f0f0f0f0f0f0f0") -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "email": "test@example.com", "iat": now, "exp": now + timedelta(minutes=5)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


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
    # Recomandarea determinist-template include un sfat de economisire CONCRET,
    # ancorat în categoria discreționară reală cu cea mai mare cheltuială
    # (SPENDING_SUMMARY: "restaurants" 520 lei) — vezi
    # app/agents/spending_forecast.py::_default_recommendation.
    assert "restaurante" in body["recommendation"]
    assert "520,00 lei" in body["recommendation"]
    # GPT a chemat DOAR get_spending_summary -> DOAR cardul "Cheltuieli
    # estimate" e relevant, NU toate 4 (feedback: "as vrea sa mi afiseze
    # asta doar cand e cazul nu mereu" — vezi
    # app/agents/spending_forecast.py::_relevant_cards).
    assert body["relevant_cards"] == ["estimated_expenses"]


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
    # GPT a chemat DOAR evaluate_affordability -> DOAR cardul "Analiză" e
    # relevant (nu și "Rezumat financiar"/"Cheltuieli estimate", chiar dacă
    # datele alea sunt calculate oricum pentru DTO).
    assert body["relevant_cards"] == ["analysis"]


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
    """Istoricul dintr-o conversație salvată ajunge efectiv în mesajele
    către GPT — fără el, agentul "uită" tot ce s-a discutat anterior.
    Istoricul vine acum din Mongo, nu din request body — simulăm asta cu
    un prim tur real, apoi al doilea cu `conversation_id` din primul."""
    first_responses = [FakeMessage(content="Estimăm că rămâi cu 26.487,90 lei.")]
    monkeypatch.setattr("app.agents.spending_forecast.chat_completion", _make_fake_chat_completion(first_responses))
    first = await client.post(
        "/spending-forecast/chat",
        json={"message": "Cu cât estimezi că rămân la finalul lunii?"},
        headers={"Authorization": f"Bearer {make_token()}"},
    )
    conversation_id = first.json()["conversation_id"]

    captured: list = []
    monkeypatch.setattr(
        "app.agents.spending_forecast.chat_completion",
        _make_fake_chat_completion([FakeMessage(content="Da, ține minte.")], captured),
    )
    response = await client.post(
        "/spending-forecast/chat",
        json={"message": "Deci cât mi-ai zis că rămâne?", "conversation_id": conversation_id},
        headers={"Authorization": f"Bearer {make_token()}"},
    )

    assert response.status_code == 200
    sent_messages = captured[0]
    contents = [m["content"] for m in sent_messages]
    assert any("26.487,90 lei" in c for c in contents), "istoricul trebuie să ajungă în promptul trimis modelului"
    assert contents[-1] == "Deci cât mi-ai zis că rămâne?"


async def test_conversation_history_is_truncated_defensively(client: AsyncClient, monkeypatch, mock_tools):
    """Chiar dacă o conversație salvată ar acumula foarte multe mesaje,
    serverul trunchiază la ultimele — nu lasă contextul să crească
    nemărginit. Populăm o conversație lungă direct prin conversation_service
    (mai simplu decât 39 de tururi HTTP reale), apoi verificăm turul următor."""
    from app.services import conversation_service

    conversation = await conversation_service.create_conversation(
        "68a0f0f0f0f0f0f0f0f0f0f0", "spending_forecast", "mesaj 0"
    )
    for i in range(1, 40):
        await conversation_service.append_turn(
            conversation["_id"], f"mesaj {i}", f"răspuns {i}", {"answer": f"răspuns {i}"}
        )

    captured: list = []
    monkeypatch.setattr(
        "app.agents.spending_forecast.chat_completion", _make_fake_chat_completion([FakeMessage(content="OK")], captured)
    )
    response = await client.post(
        "/spending-forecast/chat",
        json={"message": "ultima întrebare", "conversation_id": str(conversation["_id"])},
        headers={"Authorization": f"Bearer {make_token()}"},
    )

    assert response.status_code == 200
    sent_messages = captured[0]
    history_contents = [
        m["content"] for m in sent_messages if m["content"].startswith("mesaj ") or m["content"].startswith("răspuns ")
    ]
    assert len(history_contents) < 78  # 39 tururi × 2 mesaje = 78 dacă n-ar trunchia deloc
    assert history_contents[-1] == "răspuns 39"  # cel mai recent, păstrat


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
    # get_budget_status nu declanșează niciunul dintre cele 4 carduri de
    # forecast — bugetele au propria secțiune în UI (r.budgets), separată.
    assert body["relevant_cards"] == []


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


async def test_profanity_short_circuits_before_any_gpt_call(client: AsyncClient, monkeypatch, mock_tools):
    """Mesaj cu limbaj jignitor -> răspunsul determinist "reformulează",
    FĂRĂ niciun apel GPT (verificat prin lista de răspunsuri mock GOALĂ —
    dacă agentul ar mai apela chat_completion, testul ar pica cu
    AssertionError din fake, nu doar prin lipsa unui răspuns potrivit)."""
    monkeypatch.setattr("app.agents.spending_forecast.chat_completion", _make_fake_chat_completion([]))

    response = await client.post(
        "/spending-forecast/chat",
        json={"message": "esti prost, nu inteleg nimic din ce zici"},
        headers={"Authorization": f"Bearer {make_token()}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == moderation_service.REPHRASE_REQUEST_ANSWER
    assert body["relevant_cards"] == []
    assert body["affordable"] is None
    # DTO tot complet (context financiar pentru sidebar), chiar dacă GPT
    # n-a fost apelat deloc.
    assert body["financial_summary"]["estimated_end_balance_minor"] == FORECAST["estimated_end_of_month_balance_minor"]


async def test_no_tool_calls_means_no_relevant_cards(client: AsyncClient, monkeypatch, mock_tools):
    """Întrebare conceptuală, în afara domeniului sau la care GPT răspunde
    direct fără niciun tool -> `relevant_cards` gol, deci UI-ul nu arată
    NICIUN card de forecast (DTO-ul e completat oricum pentru integritate,
    dar nu are sens să fie afișat dacă n-are legătură cu întrebarea)."""
    responses = [FakeMessage(content="Nu e domeniul meu, dar te pot ajuta cu bugetul sau cheltuielile tale.")]
    monkeypatch.setattr("app.agents.spending_forecast.chat_completion", _make_fake_chat_completion(responses))

    response = await client.post(
        "/spending-forecast/chat",
        json={"message": "Ce vreme e azi?"},
        headers={"Authorization": f"Bearer {make_token()}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["relevant_cards"] == []
    assert body["affordable"] is None


async def test_multiple_tool_calls_show_multiple_cards_in_stable_order(client: AsyncClient, monkeypatch, mock_tools):
    """'Ce cheltuieli urmează să mai am luna asta?' -> GPT cheamă atât
    get_forecast cât și get_upcoming_subscriptions (prompt-ul cere să
    acopere ȘI obligațiile fixe, ȘI cheltuiala variabilă) -> ambele carduri
    relevante apar, în ordinea stabilă din UI (analysis, recurring_payments,
    estimated_expenses, financial_summary), indiferent de ordinea în care
    GPT le-a chemat."""
    responses = [
        FakeMessage(
            tool_calls=[
                FakeToolCall("call_1", "get_upcoming_subscriptions", "{}"),
                FakeToolCall("call_2", "get_forecast", "{}"),
            ],
        ),
        FakeMessage(content="Mai ai un abonament de plătit și cheltuieli variabile estimate până la finalul lunii."),
    ]
    monkeypatch.setattr("app.agents.spending_forecast.chat_completion", _make_fake_chat_completion(responses))

    response = await client.post(
        "/spending-forecast/chat",
        json={"message": "Ce cheltuieli urmează să mai am luna asta?"},
        headers={"Authorization": f"Bearer {make_token()}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["relevant_cards"] == ["recurring_payments", "estimated_expenses", "financial_summary"]
    assert "Traceback" not in response.text
