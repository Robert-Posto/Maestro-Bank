"""
Teste pentru accounts-service.

Rulare (cu stack-ul pornit prin `docker compose up`, bază de TEST
separată, ca să nu polueze accounts_db real):

    docker compose exec accounts-service pip install pytest==8.3.3 pytest-asyncio==0.24.0 httpx==0.27.2 -q
    docker compose exec -e MONGO_URL=mongodb://mongodb:27017/accounts_db_test accounts-service python -m pytest -q
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import get_database
from app.main import app

pytestmark = pytest.mark.asyncio


def _make_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "email": "test@example.com", "iat": now, "exp": now + timedelta(minutes=5)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


@pytest.fixture(autouse=True)
async def clean_collections():
    await get_database().accounts.delete_many({})
    await get_database().cards.delete_many({})
    yield
    await get_database().accounts.delete_many({})
    await get_database().cards.delete_many({})


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _provision(client: AsyncClient) -> tuple[str, dict]:
    user_id = str(ObjectId())  # simulăm un user_id real de auth-service (ObjectId valid)
    response = await client.post("/internal/accounts/provision", json={"user_id": user_id})
    assert response.status_code == 201
    return user_id, response.json()


async def test_account_created_with_zero_balance(client: AsyncClient):
    user_id, body = await _provision(client)
    assert body["account"]["user_id"] == user_id
    assert body["account"]["balance_minor"] == 0
    assert body["account"]["currency"] == "RON"
    assert body["account"]["status"] == "active"
    assert body["card"]["user_id"] == user_id
    assert body["card"]["type"] == "virtual"
    assert len(body["card"]["last_four"]) == 4


async def test_iban_is_unique(client: AsyncClient):
    _, first = await _provision(client)
    _, second = await _provision(client)
    assert first["account"]["iban"] != second["account"]["iban"]
    assert first["account"]["iban"].startswith("RO")
    assert "MAES" in first["account"]["iban"]


async def test_demo_funding_works(client: AsyncClient):
    user_id, _ = await _provision(client)
    token = _make_token(user_id)

    response = await client.post(
        "/dev/fund",
        json={"amount_minor": 1_000_000},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["balance_minor"] == 1_000_000
    assert response.json()["balance"] == "10000.00"


async def test_negative_funding_rejected(client: AsyncClient):
    user_id, _ = await _provision(client)
    token = _make_token(user_id)

    response = await client.post(
        "/dev/fund",
        json={"amount_minor": -500},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422  # validare Pydantic — amount_minor trebuie > 0


async def test_me_without_jwt_rejected(client: AsyncClient):
    response = await client.get("/me")
    assert response.status_code == 401
