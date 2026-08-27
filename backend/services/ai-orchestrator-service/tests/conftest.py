import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient

import app.database as db_module
from app.config import settings
from app.main import app

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def fresh_database():
    db_module.client = AsyncIOMotorClient(settings.mongo_url)
    db_module.database = db_module.client.get_default_database()
    yield
    await db_module.database.conversations.delete_many({})
    db_module.client.close()


def make_token(user_id: str = "68a0f0f0f0f0f0f0f0f0f0f0", secret: str | None = None, expired: bool = False) -> str:
    now = datetime.now(timezone.utc)
    exp = now - timedelta(minutes=1) if expired else now + timedelta(minutes=5)
    payload = {"sub": user_id, "email": "test@example.com", "iat": now, "exp": exp}
    return jwt.encode(payload, secret or settings.jwt_secret, algorithm=settings.jwt_algorithm)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_header() -> str:
    return f"Bearer {make_token()}"


# --- Fixtures pentru testele Spending + Forecast Agent (tests/test_agent.py,
# tests/test_spending_forecast_conversations.py) — mutate aici din
# test_agent.py pentru că pytest nu partajează un fixture de modul între
# fișiere de test diferite, iar noul fișier de conversații are nevoie de
# EXACT aceleași date mock (vezi task-4-brief.md, Step 2).

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


# --- Fixtures pentru testele Support Agent (tests/test_support_agent.py, --
# test_confirmation_flow.py, test_security.py) — prefixate `support_` ca
# să nu se ciocnească cu `auth_header` de mai sus (formă diferită: dict
# gata de folosit ca `headers=...` în apeluri httpx, nu doar string-ul).


def _fake_object_id() -> str:
    """String de 24 caractere hex, cu forma unui ObjectId Mongo — Support
    Agent nu are bază de date proprie, deci nu depinde de `pymongo`/`bson`
    nici măcar în teste."""
    return secrets.token_hex(12)


SUPPORT_USER_ID = _fake_object_id()
SUPPORT_OTHER_USER_ID = _fake_object_id()


@pytest.fixture
def support_auth_header() -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(SUPPORT_USER_ID)}"}


@pytest.fixture
def support_other_auth_header() -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(SUPPORT_OTHER_USER_ID)}"}


@pytest.fixture
def support_invalid_auth_header() -> dict[str, str]:
    return {"Authorization": "Bearer not-a-real-token"}


@pytest.fixture
def support_expired_auth_header() -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(SUPPORT_USER_ID, expired=True)}"}


# --- Dublură pentru SupportLLMClient (vezi app/agents/support.py) --------
# O secvență FIXĂ de răspunsuri "GPT-5-mini" — fără niciun apel de rețea
# real. Fiecare test scriptează exact ce tool-uri "alege" modelul, ca să
# poată verifica determinist orchestrarea Support Agent-ului, independent
# de comportamentul real al unui LLM.


@dataclass
class FakeFunction:
    name: str
    arguments: str


@dataclass
class FakeToolCall:
    id: str
    function: FakeFunction

    def model_dump(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.function.name, "arguments": self.function.arguments},
        }


@dataclass
class FakeMessage:
    content: str | None = None
    tool_calls: list[FakeToolCall] | None = None


def make_tool_call(name: str, arguments: dict[str, Any], call_id: str = "call_1") -> FakeToolCall:
    return FakeToolCall(id=call_id, function=FakeFunction(name=name, arguments=json.dumps(arguments)))


class FakeLLMClient:
    """Vezi docstring-ul de mai sus — implementează `SupportLLMClient`
    (interfața `.complete(messages, tools)`), fără nicio dependență de
    Azure OpenAI."""

    def __init__(self, responses: list[FakeMessage]) -> None:
        self._responses = list(responses)
        self.calls: list[list[dict[str, Any]]] = []

    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> FakeMessage:
        self.calls.append(messages)
        if not self._responses:
            raise AssertionError("FakeLLMClient: fără mai multe răspunsuri scriptate pentru acest test.")
        return self._responses.pop(0)
