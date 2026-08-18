"""
Teste pentru auth-service.

Rulare (cu stack-ul pornit prin `docker compose up`, folosind o bază de
TEST separată, ca să nu polueze datele demo reale din auth_db):

    docker compose exec auth-service pip install pytest==8.3.3 pytest-asyncio==0.24.0 -q
    docker compose exec -e MONGO_URL=mongodb://mongodb:27017/auth_db_test auth-service python -m pytest -q

Provizionarea contului bancar (apel către accounts-service) este mock-uită
aici — nu e responsabilitatea acestui serviciu să testeze accounts-service,
iar altfel testele ar crea conturi reale în accounts_db la fiecare rulare.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import get_database
from app.main import app

pytestmark = pytest.mark.asyncio

VALID_PAYLOAD = {
    "first_name": "Octavia",
    "last_name": "Test",
    "email": "octavia.autotest@maestrobank.local",
    "password": "Test1234!",
}


@pytest.fixture(autouse=True)
def mock_provisioning(monkeypatch):
    async def _noop(user_id: str) -> None:
        return None

    monkeypatch.setattr("app.routers.auth._provision_bank_account", _noop)


@pytest.fixture(autouse=True)
async def clean_users_collection():
    await get_database().users.delete_many({})
    yield
    await get_database().users.delete_many({})


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_register_creates_user(client: AsyncClient):
    response = await client.post("/auth/register", json=VALID_PAYLOAD)
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == VALID_PAYLOAD["email"]
    assert body["first_name"] == VALID_PAYLOAD["first_name"]
    assert "password_hash" not in body
    assert "password" not in body


async def test_register_duplicate_email_rejected(client: AsyncClient):
    first = await client.post("/auth/register", json=VALID_PAYLOAD)
    assert first.status_code == 201

    second = await client.post("/auth/register", json=VALID_PAYLOAD)
    assert second.status_code == 409


async def test_login_valid(client: AsyncClient):
    await client.post("/auth/register", json=VALID_PAYLOAD)

    response = await client.post(
        "/auth/login",
        json={"email": VALID_PAYLOAD["email"], "password": VALID_PAYLOAD["password"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


async def test_login_wrong_password_rejected(client: AsyncClient):
    await client.post("/auth/register", json=VALID_PAYLOAD)

    response = await client.post(
        "/auth/login",
        json={"email": VALID_PAYLOAD["email"], "password": "ParolaGresita1"},
    )
    assert response.status_code == 401


async def test_me_without_jwt_rejected(client: AsyncClient):
    response = await client.get("/auth/me")
    assert response.status_code == 401


async def test_me_with_valid_jwt(client: AsyncClient):
    await client.post("/auth/register", json=VALID_PAYLOAD)
    login_response = await client.post(
        "/auth/login",
        json={"email": VALID_PAYLOAD["email"], "password": VALID_PAYLOAD["password"]},
    )
    token = login_response.json()["access_token"]

    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == VALID_PAYLOAD["email"]
