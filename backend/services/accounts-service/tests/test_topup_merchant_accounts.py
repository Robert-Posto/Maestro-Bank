"""Teste pentru conturile-pseudo ale operatorilor de reîncărcare telefonică
(app/service.py::ensure_topup_merchant_accounts / get_topup_merchant_iban)
și ruta internă aferentă — vezi transactions-service/app/service.py
::create_topup, singurul consumator real."""

import pytest
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


async def test_ensure_topup_merchant_accounts_creates_all_four_operators():
    await service.ensure_topup_merchant_accounts()

    count = await get_database().accounts.count_documents({"is_demo_merchant": True})
    assert count == 4
    names = {
        doc["merchant_name"]
        async for doc in get_database().accounts.find({"is_demo_merchant": True})
    }
    assert names == {"Orange", "Vodafone", "Digi", "Telekom"}


async def test_ensure_topup_merchant_accounts_is_idempotent():
    await service.ensure_topup_merchant_accounts()
    await service.ensure_topup_merchant_accounts()

    count = await get_database().accounts.count_documents({"is_demo_merchant": True})
    assert count == 4


async def test_ensure_topup_merchant_accounts_skips_existing_by_name():
    # Un merchant deja existent (creat pe alt canal, ex. seed_demo_data.py)
    # NU trebuie duplicat — căutarea e după merchant_name, nu după IBAN fix.
    await get_database().accounts.insert_one(
        {
            "user_id": "merchant:topup-orange",
            "iban": "RO00PSEUDOEXISTENT0000",
            "currency": "RON",
            "balance_minor": 500,
            "status": "active",
            "is_demo_merchant": True,
            "merchant_name": "Orange",
        }
    )

    await service.ensure_topup_merchant_accounts()

    count = await get_database().accounts.count_documents({"is_demo_merchant": True, "merchant_name": "Orange"})
    assert count == 1
    stored = await get_database().accounts.find_one({"merchant_name": "Orange"})
    assert stored["iban"] == "RO00PSEUDOEXISTENT0000"
    assert stored["balance_minor"] == 500


async def test_get_topup_merchant_iban_returns_iban_for_known_operator():
    await service.ensure_topup_merchant_accounts()

    iban = await service.get_topup_merchant_iban("orange")
    assert iban is not None

    stored = await get_database().accounts.find_one({"merchant_name": "Orange"})
    assert iban == stored["iban"]


async def test_get_topup_merchant_iban_is_case_insensitive():
    await service.ensure_topup_merchant_accounts()

    assert await service.get_topup_merchant_iban("VODAFONE") == await service.get_topup_merchant_iban("vodafone")


async def test_get_topup_merchant_iban_returns_none_for_unknown_operator():
    await service.ensure_topup_merchant_accounts()

    assert await service.get_topup_merchant_iban("unknown-operator") is None


async def test_internal_endpoint_returns_iban_for_known_operator(client: AsyncClient):
    await service.ensure_topup_merchant_accounts()

    response = await client.get("/internal/accounts/topup-merchant/digi")
    assert response.status_code == 200
    body = response.json()
    assert body["iban"]

    stored = await get_database().accounts.find_one({"merchant_name": "Digi"})
    assert body["iban"] == stored["iban"]


async def test_internal_endpoint_returns_404_for_unknown_operator(client: AsyncClient):
    response = await client.get("/internal/accounts/topup-merchant/lyca-mobile")
    assert response.status_code == 404
