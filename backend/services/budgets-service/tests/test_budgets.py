"""
Teste pentru budgets-service.

Rulare (cu stack-ul pornit prin `docker compose up`, bază de TEST
separată, ca să nu polueze budgets_db real):

    docker compose exec budgets-service pip install pytest==8.3.3 pytest-asyncio==0.24.0 httpx==0.27.2 -q
    docker compose exec -e MONGO_URL=mongodb://mongodb:27017/budgets_db_test budgets-service python -m pytest -q
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
async def clean_collections():
    await get_database().budgets.delete_many({})
    await get_database().subscriptions.delete_many({})
    yield
    await get_database().budgets.delete_many({})
    await get_database().subscriptions.delete_many({})


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --- Budgets -----------------------------------------------------------------


async def test_create_budget(client: AsyncClient):
    response = await client.post(
        "/budgets",
        json={"name": "Groceries", "category": "groceries", "limit_minor": 100_000, "period": "monthly"},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Groceries"
    assert body["limit_minor"] == 100_000
    assert body["active"] is True


async def test_create_budget_requires_jwt(client: AsyncClient):
    response = await client.post(
        "/budgets", json={"name": "Groceries", "category": "groceries", "limit_minor": 100_000}
    )
    assert response.status_code == 401


async def test_list_budgets_isolation(client: AsyncClient):
    await client.post(
        "/budgets", json={"name": "Groceries", "category": "groceries", "limit_minor": 100_000}, headers=AUTH_HEADER
    )

    mine = await client.get("/budgets", headers=AUTH_HEADER)
    assert len(mine.json()) == 1

    others = await client.get("/budgets", headers=OTHER_AUTH_HEADER)
    assert others.json() == []


async def test_update_budget(client: AsyncClient):
    created = await client.post(
        "/budgets", json={"name": "Groceries", "category": "groceries", "limit_minor": 100_000}, headers=AUTH_HEADER
    )
    budget_id = created.json()["id"]

    response = await client.patch(f"/budgets/{budget_id}", json={"limit_minor": 150_000}, headers=AUTH_HEADER)
    assert response.status_code == 200
    assert response.json()["limit_minor"] == 150_000


async def test_update_budget_user_isolation(client: AsyncClient):
    created = await client.post(
        "/budgets", json={"name": "Groceries", "category": "groceries", "limit_minor": 100_000}, headers=AUTH_HEADER
    )
    budget_id = created.json()["id"]

    response = await client.patch(f"/budgets/{budget_id}", json={"limit_minor": 1}, headers=OTHER_AUTH_HEADER)
    assert response.status_code == 404


async def test_delete_budget(client: AsyncClient):
    created = await client.post(
        "/budgets", json={"name": "Groceries", "category": "groceries", "limit_minor": 100_000}, headers=AUTH_HEADER
    )
    budget_id = created.json()["id"]

    response = await client.delete(f"/budgets/{budget_id}", headers=AUTH_HEADER)
    assert response.status_code == 204

    listed = await client.get("/budgets", headers=AUTH_HEADER)
    assert listed.json() == []


async def test_delete_budget_user_isolation(client: AsyncClient):
    created = await client.post(
        "/budgets", json={"name": "Groceries", "category": "groceries", "limit_minor": 100_000}, headers=AUTH_HEADER
    )
    budget_id = created.json()["id"]

    response = await client.delete(f"/budgets/{budget_id}", headers=OTHER_AUTH_HEADER)
    assert response.status_code == 404


# --- Subscriptions -------------------------------------------------------------


async def test_create_subscription(client: AsyncClient):
    response = await client.post(
        "/subscriptions",
        json={"name": "Netflix", "amount_minor": 3999, "billing_day": 24, "category": "subscriptions"},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Netflix"
    assert response.json()["active"] is True


async def test_list_subscriptions_isolation(client: AsyncClient):
    await client.post(
        "/subscriptions", json={"name": "Netflix", "amount_minor": 3999, "billing_day": 24}, headers=AUTH_HEADER
    )

    mine = await client.get("/subscriptions", headers=AUTH_HEADER)
    assert len(mine.json()) == 1

    others = await client.get("/subscriptions", headers=OTHER_AUTH_HEADER)
    assert others.json() == []


async def test_update_and_delete_subscription(client: AsyncClient):
    created = await client.post(
        "/subscriptions", json={"name": "Netflix", "amount_minor": 3999, "billing_day": 24}, headers=AUTH_HEADER
    )
    subscription_id = created.json()["id"]

    updated = await client.patch(
        f"/subscriptions/{subscription_id}", json={"active": False}, headers=AUTH_HEADER
    )
    assert updated.status_code == 200
    assert updated.json()["active"] is False

    deleted = await client.delete(f"/subscriptions/{subscription_id}", headers=AUTH_HEADER)
    assert deleted.status_code == 204


# --- Internal (transactions-service forecast) ---------------------------------


async def test_internal_active_subscriptions_by_user(client: AsyncClient):
    await client.post(
        "/subscriptions", json={"name": "Netflix", "amount_minor": 3999, "billing_day": 24}, headers=AUTH_HEADER
    )
    inactive = await client.post(
        "/subscriptions", json={"name": "Old gym", "amount_minor": 5000, "billing_day": 5}, headers=AUTH_HEADER
    )
    await client.patch(f"/subscriptions/{inactive.json()['id']}", json={"active": False}, headers=AUTH_HEADER)

    response = await client.get(f"/internal/budgets/subscriptions/by-user/{USER_ID}")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "Netflix"
