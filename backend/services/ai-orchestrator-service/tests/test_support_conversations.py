"""
Rulare: vezi header-ul tests/test_conversation_service.py.
"""

import jwt
import pytest

from app.config import settings
from app.services import conversation_service

pytestmark = pytest.mark.asyncio


def _user_id_from_auth_header(auth_header: dict[str, str]) -> str:
    """Extrage `sub` din tokenul JWT dintr-un fixture `support_auth_header`-like,
    ca să putem seeda o conversație direct prin conversation_service (fără o
    tură HTTP reală) pentru ACELAȘI user pe care ni-l dă fixture-ul."""
    token = auth_header["Authorization"].split(" ", 1)[1]
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    return payload["sub"]


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


async def test_chat_succeeds_after_stored_history_exceeds_field_cap(client, support_auth_header, monkeypatch):
    """Regresie: ChatRequest.history are max_length=40 (vezi
    app/models/support.py), dar istoricul stocat în Mongo NU e plafonat
    (append_turn face un $push necondiționat) — o conversație lungă poate
    depăși cu ușurință 40 de mesaje stocate (~21+ ture). Router-ul trebuie
    să trunchieze istoricul ÎNAINTE de a reconstrui ChatRequest, altfel
    Pydantic aruncă ValidationError aici, necaptat de handlerele existente
    (RuntimeError/APIError) → 500 brut pentru un chat de suport normal, doar
    mai lung. Seedăm direct prin conversation_service (nu prin 25+ ture HTTP
    reale), ca la test_agent.py::test_long_history_is_truncated..."""
    user_id = _user_id_from_auth_header(support_auth_header)
    conversation = await conversation_service.create_conversation(user_id, "support", "prima întrebare")
    for i in range(25):
        await conversation_service.append_turn(
            conversation["_id"], f"mesaj utilizator {i}", f"răspuns asistent {i}", {}
        )
    # 25 ture * 2 mesaje/tură = 50 mesaje stocate > 40 (limita câmpului).

    monkeypatch.setattr("app.agents.support._default_llm_client.complete", _fake_complete("Ok, am înțeles."))
    response = await client.post(
        "/support",
        json={"message": "O întrebare nouă după un istoric lung", "conversation_id": str(conversation["_id"])},
        headers=support_auth_header,
    )
    assert response.status_code == 200
    assert response.json()["conversation_id"] == str(conversation["_id"])
