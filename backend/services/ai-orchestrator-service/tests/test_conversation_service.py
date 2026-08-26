"""
Rulare (cu stack-ul pornit prin `docker compose up`, bază de TEST separată):

    docker compose exec ai-orchestrator-service pip install pytest==8.3.3 pytest-asyncio==0.24.0 httpx==0.27.2 -q
    docker compose exec -e MONGO_URL=mongodb://mongodb:27017/ai_orchestrator_db_test ai-orchestrator-service python -m pytest -q
"""

import pytest
from fastapi import HTTPException

from app.services import conversation_service

pytestmark = pytest.mark.asyncio

USER_ID = "68a0f0f0f0f0f0f0f0f0f0f0"
OTHER_USER_ID = "68a0f0f0f0f0f0f0f0f0f0f1"


async def test_create_conversation_sets_title_from_first_message():
    conversation = await conversation_service.create_conversation(USER_ID, "spending_forecast", "Îmi permit un city break de 2000 lei?")
    assert conversation["title"] == "Îmi permit un city break de 2000 lei?"
    assert conversation["agent"] == "spending_forecast"
    assert conversation["user_id"] == USER_ID
    assert conversation["messages"] == []


async def test_create_conversation_truncates_long_title():
    long_message = "a" * 80
    conversation = await conversation_service.create_conversation(USER_ID, "support", long_message)
    assert conversation["title"] == "a" * 50 + "…"


async def test_list_conversations_scoped_to_user_and_agent():
    await conversation_service.create_conversation(USER_ID, "spending_forecast", "primul mesaj")
    await conversation_service.create_conversation(USER_ID, "support", "alt agent")
    await conversation_service.create_conversation(OTHER_USER_ID, "spending_forecast", "alt user")

    mine = await conversation_service.list_conversations(USER_ID, "spending_forecast")
    assert len(mine) == 1
    assert mine[0]["title"] == "primul mesaj"


async def test_list_conversations_sorted_by_updated_at_desc():
    first = await conversation_service.create_conversation(USER_ID, "spending_forecast", "primul")
    second = await conversation_service.create_conversation(USER_ID, "spending_forecast", "al doilea")

    conversations = await conversation_service.list_conversations(USER_ID, "spending_forecast")
    assert [c["_id"] for c in conversations] == [second["_id"], first["_id"]]


async def test_get_conversation_returns_owned_conversation():
    created = await conversation_service.create_conversation(USER_ID, "support", "bună")
    fetched = await conversation_service.get_conversation(USER_ID, "support", str(created["_id"]))
    assert fetched["_id"] == created["_id"]


async def test_get_conversation_404_for_wrong_user():
    created = await conversation_service.create_conversation(USER_ID, "support", "bună")
    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.get_conversation(OTHER_USER_ID, "support", str(created["_id"]))
    assert exc_info.value.status_code == 404


async def test_get_conversation_404_for_wrong_agent():
    created = await conversation_service.create_conversation(USER_ID, "support", "bună")
    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.get_conversation(USER_ID, "spending_forecast", str(created["_id"]))
    assert exc_info.value.status_code == 404


async def test_get_conversation_400_for_malformed_id():
    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.get_conversation(USER_ID, "support", "not-an-object-id")
    assert exc_info.value.status_code == 400


async def test_append_turn_adds_both_messages_and_bumps_updated_at():
    created = await conversation_service.create_conversation(USER_ID, "spending_forecast", "prima întrebare")
    original_updated_at = created["updated_at"]

    await conversation_service.append_turn(
        created["_id"], "prima întrebare", "răspunsul agentului", {"answer": "răspunsul agentului"}
    )

    reloaded = await conversation_service.get_conversation(USER_ID, "spending_forecast", str(created["_id"]))
    assert len(reloaded["messages"]) == 2
    assert reloaded["messages"][0] == {
        "role": "user",
        "content": "prima întrebare",
        "response": None,
        "created_at": reloaded["messages"][0]["created_at"],
    }
    assert reloaded["messages"][1]["role"] == "assistant"
    assert reloaded["messages"][1]["response"] == {"answer": "răspunsul agentului"}
    assert reloaded["updated_at"] >= original_updated_at


async def test_to_history_dicts_strips_response_and_created_at():
    created = await conversation_service.create_conversation(USER_ID, "spending_forecast", "întrebare")
    await conversation_service.append_turn(created["_id"], "întrebare", "răspuns", {"answer": "răspuns"})
    reloaded = await conversation_service.get_conversation(USER_ID, "spending_forecast", str(created["_id"]))

    history = conversation_service.to_history_dicts(reloaded)
    assert history == [
        {"role": "user", "content": "întrebare"},
        {"role": "assistant", "content": "răspuns"},
    ]


async def test_delete_conversation_removes_it():
    created = await conversation_service.create_conversation(USER_ID, "support", "de șters")
    await conversation_service.delete_conversation(USER_ID, "support", str(created["_id"]))

    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.get_conversation(USER_ID, "support", str(created["_id"]))
    assert exc_info.value.status_code == 404


async def test_delete_conversation_404_for_wrong_user():
    created = await conversation_service.create_conversation(USER_ID, "support", "nu al tău")
    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.delete_conversation(OTHER_USER_ID, "support", str(created["_id"]))
    assert exc_info.value.status_code == 404
