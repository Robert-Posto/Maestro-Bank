"""
Teste pentru support-service.

Rulare (cu stack-ul pornit prin `docker compose up`, bază de TEST
separată, ca să nu polueze support_db real):

    docker compose exec support-service pip install pytest==8.3.3 pytest-asyncio==0.24.0 httpx==0.27.2 -q
    docker compose exec -e MONGO_URL=mongodb://mongodb:27017/support_db_test support-service python -m pytest -q
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

USER_ID = str(ObjectId())
OTHER_USER_ID = str(ObjectId())


def _make_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "email": "test@example.com", "iat": now, "exp": now + timedelta(minutes=5)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


AUTH_HEADER = {"Authorization": f"Bearer {_make_token(USER_ID)}"}
OTHER_AUTH_HEADER = {"Authorization": f"Bearer {_make_token(OTHER_USER_ID)}"}


@pytest.fixture(autouse=True)
async def clean_tickets():
    await get_database().tickets.delete_many({})
    yield
    await get_database().tickets.delete_many({})


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_create_ticket(client: AsyncClient):
    response = await client.post(
        "/tickets",
        json={"subject": "Cardul nu merge", "category": "card", "message": "Cardul a fost respins la POS."},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["subject"] == "Cardul nu merge"
    assert body["status"] == "open"
    assert body["category"] == "card"


async def test_create_ticket_requires_jwt(client: AsyncClient):
    response = await client.post("/tickets", json={"subject": "x", "category": "other", "message": "y"})
    assert response.status_code == 401


async def test_list_my_tickets(client: AsyncClient):
    await client.post(
        "/tickets", json={"subject": "Card", "category": "card", "message": "Detalii"}, headers=AUTH_HEADER
    )
    await client.post(
        "/tickets", json={"subject": "Cont", "category": "account", "message": "Detalii"}, headers=AUTH_HEADER
    )

    response = await client.get("/tickets", headers=AUTH_HEADER)
    assert response.status_code == 200
    assert len(response.json()) == 2


async def test_cannot_see_another_users_tickets(client: AsyncClient):
    await client.post(
        "/tickets", json={"subject": "Card", "category": "card", "message": "Detalii"}, headers=AUTH_HEADER
    )

    response = await client.get("/tickets", headers=OTHER_AUTH_HEADER)
    assert response.status_code == 200
    assert response.json() == []


async def test_get_ticket_by_id(client: AsyncClient):
    created = await client.post(
        "/tickets", json={"subject": "Card", "category": "card", "message": "Detalii"}, headers=AUTH_HEADER
    )
    ticket_id = created.json()["id"]

    response = await client.get(f"/tickets/{ticket_id}", headers=AUTH_HEADER)
    assert response.status_code == 200
    assert response.json()["subject"] == "Card"


async def test_cannot_get_another_users_ticket_by_id(client: AsyncClient):
    created = await client.post(
        "/tickets", json={"subject": "Card", "category": "card", "message": "Detalii"}, headers=AUTH_HEADER
    )
    ticket_id = created.json()["id"]

    response = await client.get(f"/tickets/{ticket_id}", headers=OTHER_AUTH_HEADER)
    assert response.status_code == 404
