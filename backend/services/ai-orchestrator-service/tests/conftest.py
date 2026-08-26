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
