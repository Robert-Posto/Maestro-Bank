"""Teste pentru contul-pseudo de reținere fraud (app/service.py
::ensure_fraud_holding_account / get_fraud_holding_account_id) și ruta
internă aferentă — vezi transactions-service/app/holds.py, care e
singurul consumator real."""

import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from app import service
from app.database import get_database
from app.main import app

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def clean_collections():
    await get_database().accounts.delete_many({})
    yield
    await get_database().accounts.delete_many({})


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_ensure_fraud_holding_account_creates_exactly_one():
    account_id = await service.ensure_fraud_holding_account()
    assert account_id

    stored = await get_database().accounts.find_one({"_id": ObjectId(account_id)})
    assert stored is not None
    assert stored["is_fraud_holding_account"] is True
    assert stored["balance_minor"] == 0
    assert stored["status"] == "active"


async def test_ensure_fraud_holding_account_is_idempotent():
    first_id = await service.ensure_fraud_holding_account()
    second_id = await service.ensure_fraud_holding_account()
    assert first_id == second_id

    count = await get_database().accounts.count_documents({"is_fraud_holding_account": True})
    assert count == 1


async def test_get_fraud_holding_account_id_creates_if_missing():
    # NU apelăm ensure_fraud_holding_account întâi — get_ trebuie să se
    # descurce singur (vezi service.py, ramura defensivă).
    account_id = await service.get_fraud_holding_account_id()
    assert account_id
    stored = await get_database().accounts.find_one({"is_fraud_holding_account": True})
    assert str(stored["_id"]) == account_id


async def test_internal_endpoint_returns_holding_account_id(client: AsyncClient):
    response = await client.get("/internal/accounts/fraud-holding-account")
    assert response.status_code == 200
    body = response.json()
    assert body["account_id"]

    stored = await get_database().accounts.find_one({"is_fraud_holding_account": True})
    assert str(stored["_id"]) == body["account_id"]
