"""
Rulare: vezi header-ul tests/test_conversation_service.py pentru comanda
completă (aceeași bază de test, `ai_orchestrator_db_test`).
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from httpx import AsyncClient

from app.config import settings

pytestmark = pytest.mark.asyncio


def make_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "email": "test@example.com", "iat": now, "exp": now + timedelta(minutes=5)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


USER_ID = "68a0f0f0f0f0f0f0f0f0f0f0"
OTHER_USER_ID = "68a0f0f0f0f0f0f0f0f0f0f1"


class FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


def _fake_chat_completion(answer: str):
    async def fake(messages, tools=None):
        return FakeMessage(content=answer)

    return fake


async def test_chat_without_conversation_id_creates_one(client: AsyncClient, monkeypatch, mock_tools):
    monkeypatch.setattr("app.agents.spending_forecast.chat_completion", _fake_chat_completion("Bună ziua!"))

    response = await client.post(
        "/spending-forecast/chat", json={"message": "Bună"}, headers={"Authorization": f"Bearer {make_token(USER_ID)}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"]
    assert body["answer"] == "Bună ziua!"


async def test_chat_reuses_existing_conversation(client: AsyncClient, monkeypatch, mock_tools):
    monkeypatch.setattr("app.agents.spending_forecast.chat_completion", _fake_chat_completion("Primul răspuns"))
    first = await client.post(
        "/spending-forecast/chat", json={"message": "Primul mesaj"}, headers={"Authorization": f"Bearer {make_token(USER_ID)}"}
    )
    conversation_id = first.json()["conversation_id"]

    monkeypatch.setattr("app.agents.spending_forecast.chat_completion", _fake_chat_completion("Al doilea răspuns"))
    second = await client.post(
        "/spending-forecast/chat",
        json={"message": "Al doilea mesaj", "conversation_id": conversation_id},
        headers={"Authorization": f"Bearer {make_token(USER_ID)}"},
    )
    assert second.status_code == 200
    assert second.json()["conversation_id"] == conversation_id

    detail = await client.get(
        f"/spending-forecast/conversations/{conversation_id}", headers={"Authorization": f"Bearer {make_token(USER_ID)}"}
    )
    contents = [m["content"] for m in detail.json()["messages"]]
    assert contents == ["Primul mesaj", "Primul răspuns", "Al doilea mesaj", "Al doilea răspuns"]


async def test_list_conversations_returns_only_mine(client: AsyncClient, monkeypatch, mock_tools):
    monkeypatch.setattr("app.agents.spending_forecast.chat_completion", _fake_chat_completion("a"))
    await client.post("/spending-forecast/chat", json={"message": "a mea"}, headers={"Authorization": f"Bearer {make_token(USER_ID)}"})

    monkeypatch.setattr("app.agents.spending_forecast.chat_completion", _fake_chat_completion("b"))
    await client.post(
        "/spending-forecast/chat", json={"message": "a altcuiva"}, headers={"Authorization": f"Bearer {make_token(OTHER_USER_ID)}"}
    )

    response = await client.get("/spending-forecast/conversations", headers={"Authorization": f"Bearer {make_token(USER_ID)}"})
    assert [c["title"] for c in response.json()] == ["a mea"]


async def test_get_conversation_404_for_other_user(client: AsyncClient, monkeypatch, mock_tools):
    monkeypatch.setattr("app.agents.spending_forecast.chat_completion", _fake_chat_completion("privat"))
    created = await client.post(
        "/spending-forecast/chat", json={"message": "privat"}, headers={"Authorization": f"Bearer {make_token(USER_ID)}"}
    )
    conversation_id = created.json()["conversation_id"]

    response = await client.get(
        f"/spending-forecast/conversations/{conversation_id}", headers={"Authorization": f"Bearer {make_token(OTHER_USER_ID)}"}
    )
    assert response.status_code == 404


async def test_delete_conversation(client: AsyncClient, monkeypatch, mock_tools):
    monkeypatch.setattr("app.agents.spending_forecast.chat_completion", _fake_chat_completion("de șters"))
    created = await client.post(
        "/spending-forecast/chat", json={"message": "de șters"}, headers={"Authorization": f"Bearer {make_token(USER_ID)}"}
    )
    conversation_id = created.json()["conversation_id"]

    delete_response = await client.delete(
        f"/spending-forecast/conversations/{conversation_id}", headers={"Authorization": f"Bearer {make_token(USER_ID)}"}
    )
    assert delete_response.status_code == 204

    get_response = await client.get(
        f"/spending-forecast/conversations/{conversation_id}", headers={"Authorization": f"Bearer {make_token(USER_ID)}"}
    )
    assert get_response.status_code == 404
