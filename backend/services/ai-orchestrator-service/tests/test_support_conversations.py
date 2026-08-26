"""
Rulare: vezi header-ul tests/test_conversation_service.py.
"""

import pytest

pytestmark = pytest.mark.asyncio


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content
        self.tool_calls = []


def _fake_complete(answer: str):
    async def complete(messages, tools):
        return _FakeMessage(answer)

    return complete


async def test_chat_without_conversation_id_creates_one(client, support_auth_header, monkeypatch):
    monkeypatch.setattr("app.agents.support._default_llm_client.complete", _fake_complete("Bună ziua!"))

    response = await client.post("/support", json={"message": "Bună"}, headers=support_auth_header)
    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"]
    assert body["answer"] == "Bună ziua!"


async def test_chat_reuses_existing_conversation(client, support_auth_header, monkeypatch):
    monkeypatch.setattr("app.agents.support._default_llm_client.complete", _fake_complete("Primul răspuns"))
    first = await client.post("/support", json={"message": "Primul mesaj"}, headers=support_auth_header)
    conversation_id = first.json()["conversation_id"]

    monkeypatch.setattr("app.agents.support._default_llm_client.complete", _fake_complete("Al doilea răspuns"))
    second = await client.post(
        "/support", json={"message": "Al doilea mesaj", "conversation_id": conversation_id}, headers=support_auth_header
    )
    assert second.json()["conversation_id"] == conversation_id

    detail = await client.get(f"/support/conversations/{conversation_id}", headers=support_auth_header)
    contents = [m["content"] for m in detail.json()["messages"]]
    assert contents == ["Primul mesaj", "Primul răspuns", "Al doilea mesaj", "Al doilea răspuns"]


async def test_list_conversations_returns_only_mine(client, support_auth_header, support_other_auth_header, monkeypatch):
    monkeypatch.setattr("app.agents.support._default_llm_client.complete", _fake_complete("a"))
    await client.post("/support", json={"message": "a mea"}, headers=support_auth_header)

    monkeypatch.setattr("app.agents.support._default_llm_client.complete", _fake_complete("b"))
    await client.post("/support", json={"message": "a altcuiva"}, headers=support_other_auth_header)

    response = await client.get("/support/conversations", headers=support_auth_header)
    titles = [c["title"] for c in response.json()]
    assert titles == ["a mea"]


async def test_get_conversation_404_for_other_user(client, support_auth_header, support_other_auth_header, monkeypatch):
    monkeypatch.setattr("app.agents.support._default_llm_client.complete", _fake_complete("privat"))
    created = await client.post("/support", json={"message": "privat"}, headers=support_auth_header)
    conversation_id = created.json()["conversation_id"]

    response = await client.get(f"/support/conversations/{conversation_id}", headers=support_other_auth_header)
    assert response.status_code == 404


async def test_delete_conversation(client, support_auth_header, monkeypatch):
    monkeypatch.setattr("app.agents.support._default_llm_client.complete", _fake_complete("de șters"))
    created = await client.post("/support", json={"message": "de șters"}, headers=support_auth_header)
    conversation_id = created.json()["conversation_id"]

    delete_response = await client.delete(f"/support/conversations/{conversation_id}", headers=support_auth_header)
    assert delete_response.status_code == 204

    get_response = await client.get(f"/support/conversations/{conversation_id}", headers=support_auth_header)
    assert get_response.status_code == 404
