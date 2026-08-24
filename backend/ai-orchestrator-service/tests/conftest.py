"""Fixtures comune pentru testele Support Agent.

NICIUN test din acest pachet nu face un apel real către Azure OpenAI —
`FakeLLMClient` de mai jos e o dublură scriptată, injectată explicit în
`support_service.handle_chat(..., llm_client=...)` / `run_support_agent`,
exact ca `AzureOpenAIClient` reală, dar fără rețea și fără cheie.

Apelurile către Gateway (app/tools/*) sunt mock-uite per-test cu
`monkeypatch.setattr`, la fel ca în restul microserviciilor din proiect
(vezi backend/services/auth-service/tests/test_auth.py).
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import pytest

from app.config import settings


def _fake_object_id() -> str:
    """String de 24 caractere hex, cu forma unui ObjectId Mongo — Support
    Agent nu are bază de date proprie (vezi app/config.py), deci nu
    depinde de `pymongo`/`bson` nici măcar în teste."""
    return secrets.token_hex(12)


USER_ID = _fake_object_id()
OTHER_USER_ID = _fake_object_id()


def make_token(user_id: str, secret: str | None = None, expired: bool = False) -> str:
    now = datetime.now(timezone.utc)
    exp = now - timedelta(minutes=1) if expired else now + timedelta(minutes=5)
    payload = {"sub": user_id, "email": "test@example.com", "iat": now, "exp": exp}
    return jwt.encode(payload, secret or settings.jwt_secret, algorithm=settings.jwt_algorithm)


@pytest.fixture
def auth_header() -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(USER_ID)}"}


@pytest.fixture
def other_auth_header() -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(OTHER_USER_ID)}"}


@pytest.fixture
def invalid_auth_header() -> dict[str, str]:
    return {"Authorization": "Bearer not-a-real-token"}


@pytest.fixture
def expired_auth_header() -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(USER_ID, expired=True)}"}


# --- Dublură pentru AzureOpenAIClient (vezi app/llm/azure_openai.py) -----


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
    """O secvență FIXĂ de răspunsuri "GPT-5-mini" — fără niciun apel de
    rețea real. Fiecare test scriptează exact ce tool-uri "alege" modelul,
    ca să poată verifica determinist orchestrarea (app/agents/support.py +
    app/services/support_service.py), independent de comportamentul real
    al unui LLM."""

    def __init__(self, responses: list[FakeMessage]) -> None:
        self._responses = list(responses)
        self.calls: list[list[dict[str, Any]]] = []

    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> FakeMessage:
        self.calls.append(messages)
        if not self._responses:
            raise AssertionError("FakeLLMClient: fără mai multe răspunsuri scriptate pentru acest test.")
        return self._responses.pop(0)
