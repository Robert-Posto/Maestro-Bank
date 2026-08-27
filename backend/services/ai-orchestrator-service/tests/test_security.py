"""Teste de securitate — vezi task-ul MaestroBank, secțiunea 28.

Rulare (din interiorul containerului ai-orchestrator-service):

    docker compose exec ai-orchestrator-service pip install -r requirements-dev.txt -q
    docker compose exec ai-orchestrator-service python -m pytest -q
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.security import get_current_user_id
from app.services.moderation_service import REPHRASE_REQUEST_ANSWER
from app.tools import support_accounts_tools
from tests.conftest import make_token

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_no_jwt_returns_401(client: AsyncClient):
    response = await client.post("/support", json={"message": "Cardul meu este activ?"})
    assert response.status_code == 401


async def test_invalid_jwt_returns_401(client: AsyncClient, support_invalid_auth_header: dict[str, str]):
    response = await client.post("/support", json={"message": "Cardul meu este activ?"}, headers=support_invalid_auth_header)
    assert response.status_code == 401


async def test_expired_jwt_returns_401(client: AsyncClient, support_expired_auth_header: dict[str, str]):
    response = await client.post("/support", json={"message": "Cardul meu este activ?"}, headers=support_expired_auth_header)
    assert response.status_code == 401


async def test_malformed_authorization_header_returns_401(client: AsyncClient):
    response = await client.post(
        "/support", json={"message": "Cardul meu este activ?"}, headers={"Authorization": "not-bearer-format"}
    )
    assert response.status_code == 401


async def test_profanity_gets_deterministic_reply_without_calling_llm(
    monkeypatch, client: AsyncClient, support_auth_header: dict[str, str]
):
    """Limbaj jignitor -> răspuns determinist ("reformulează"), FĂRĂ niciun
    apel GPT — vezi app/services/support_service.py și moderation_service.py
    (același filtru folosit și de Spending + Forecast Agent)."""

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("LLM-ul NU trebuie apelat pentru un mesaj cu limbaj jignitor.")

    monkeypatch.setattr("app.agents.support._default_llm_client.complete", fail_if_called)

    response = await client.post(
        "/support", json={"message": "esti prost, nu inteleg nimic"}, headers=support_auth_header
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == REPHRASE_REQUEST_ANSWER
    assert body["requires_confirmation"] is False


async def test_tools_never_send_user_id_only_forward_authorization(monkeypatch, support_auth_header: dict[str, str]):
    """User A nu poate cere "arată-mi contul lui B" și primi date reale —
    izolarea vine STRICT din header-ul Authorization propagat neschimbat
    către Gateway; tool-urile nu acceptă și nu trimit niciodată un user_id
    explicit. Verificăm asta la nivelul apelului HTTP real (mock-uit)."""
    captured: dict = {}

    async def fake_gateway_request(method, path, authorization, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["authorization"] = authorization
        captured["kwargs"] = kwargs
        return {"id": "acc1", "iban": "RO00MAES0000", "balance_minor": 1000, "status": "active"}

    monkeypatch.setattr("app.tools.support_accounts_tools.gateway_request", fake_gateway_request)

    result = await support_accounts_tools.get_my_account(support_auth_header["Authorization"])

    assert result["iban"] == "RO00MAES0000"
    assert captured["authorization"] == support_auth_header["Authorization"]
    assert "user_id" not in captured["kwargs"]
    assert "user_id" not in captured["path"]


async def test_get_current_user_id_returns_sub_claim():
    user_id = "68a0f0f0f0f0f0f0f0f0f0f0"
    token = make_token(user_id)
    result = await get_current_user_id(authorization=f"Bearer {token}")
    assert result == user_id


async def test_get_current_user_id_rejects_missing_header():
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_id(authorization=None)
    assert exc_info.value.status_code == 401


async def test_get_current_user_id_rejects_invalid_token():
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_id(authorization="Bearer not-a-real-token")
    assert exc_info.value.status_code == 401
