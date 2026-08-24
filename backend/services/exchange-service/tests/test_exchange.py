"""
Teste pentru exchange-service (motor FX DEMO).

Rulare (cu stack-ul pornit prin `docker compose up`, bază de TEST
separată, ca să nu polueze exchange_db real):

    docker compose exec exchange-service pip install pytest==8.3.3 pytest-asyncio==0.24.0 httpx==0.27.2 -q
    docker compose exec -e MONGO_URL=mongodb://mongodb:27017/exchange_db_test exchange-service python -m pytest -q
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import jwt
import pytest
from bson import ObjectId
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import get_database
from app.main import app

pytestmark = pytest.mark.asyncio

USER_ID = str(ObjectId())


def _make_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "email": "test@example.com", "iat": now, "exp": now + timedelta(minutes=5)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


AUTH_HEADER = {"Authorization": f"Bearer {_make_token(USER_ID)}"}


@pytest.fixture(autouse=True)
async def clean_collections():
    await get_database().demo_exchanges.delete_many({})
    await get_database().daily_rates.delete_many({})
    yield
    await get_database().demo_exchanges.delete_many({})
    await get_database().daily_rates.delete_many({})


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_rates_require_jwt(client: AsyncClient):
    response = await client.get("/rates")
    assert response.status_code == 401


async def test_get_rates(client: AsyncClient):
    response = await client.get("/rates", headers=AUTH_HEADER)
    assert response.status_code == 200
    body = response.json()
    assert len(body) > 0
    assert all(rate["mid_rate"] > 0 for rate in body)


async def test_quote_ron_to_eur(client: AsyncClient):
    response = await client.get(
        "/quote", params={"from_currency": "RON", "to_currency": "EUR", "amount_minor": 500_000}, headers=AUTH_HEADER
    )
    assert response.status_code == 200
    body = response.json()
    assert body["received_minor"] > 0
    assert body["received_minor"] < body["amount_minor"]  # curs > 1, deci mai puține unități EUR decât bani RON
    assert body["total_cost_minor"] > 0


async def test_quote_unsupported_pair_rejected(client: AsyncClient):
    response = await client.get(
        "/quote", params={"from_currency": "EUR", "to_currency": "USD", "amount_minor": 1_000}, headers=AUTH_HEADER
    )
    assert response.status_code == 400


async def test_rates_fall_back_to_demo_when_bnr_unavailable(client: AsyncClient, monkeypatch):
    """Fără niciun curs BNR salvat în DB (fetch eșuat/nerulat încă) ->
    cade pe fallback-ul demo static, nu lasă pagina goală/eroare."""

    async def fake_fetch_bnr_rates():
        raise ConnectionError("BNR indisponibil (simulat în test)")

    monkeypatch.setattr("app.service.fetch_bnr_rates", fake_fetch_bnr_rates)

    response = await client.get("/rates", headers=AUTH_HEADER)
    assert response.status_code == 200
    body = response.json()
    assert all(rate["source"] == "demo-fallback" for rate in body)
    assert all(rate["mid_rate"] > 0 for rate in body)


async def test_rates_use_bnr_after_successful_refresh(client: AsyncClient, monkeypatch):
    """După un refresh BNR reușit, /rates raportează sursa 'BNR' cu cursul primit."""

    async def fake_fetch_bnr_rates():
        return {"EUR": 5.1234, "USD": 4.7, "GBP": 5.9}, "2026-08-19"

    monkeypatch.setattr("app.service.fetch_bnr_rates", fake_fetch_bnr_rates)

    from app.service import refresh_rates_from_bnr

    refreshed = await refresh_rates_from_bnr()
    assert refreshed is True

    response = await client.get("/rates", headers=AUTH_HEADER)
    body = response.json()
    eur = next(r for r in body if r["currency"] == "EUR")
    assert eur["source"] == "BNR"
    assert eur["mid_rate"] == 5.1234


async def test_execute_exchange_is_recorded_and_isolated(client: AsyncClient, monkeypatch):
    """apply_internal_exchange (accounts-service) e mock-uit — testat separat,
    la nivelul lui, în accounts-service; aici verificăm doar wiring-ul
    exchange-service-ului (execuție -> înregistrare -> istoric per user)."""
    mock_apply = AsyncMock(return_value=None)
    monkeypatch.setattr("app.service._apply_exchange_in_accounts_service", mock_apply)

    other_user_token = f"Bearer {_make_token(str(ObjectId()))}"

    response = await client.post(
        "/execute",
        json={"from_currency": "RON", "to_currency": "EUR", "amount_minor": 500_000},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["from_currency"] == "RON"
    assert body["to_currency"] == "EUR"
    mock_apply.assert_awaited_once()

    mine = await client.get("/history", headers=AUTH_HEADER)
    assert len(mine.json()) == 1

    others = await client.get("/history", headers={"Authorization": other_user_token})
    assert others.json() == []


async def test_execute_exchange_propagates_missing_account_error(client: AsyncClient, monkeypatch):
    """Dacă userul n-are încă un cont pe valuta țintă, accounts-service
    întoarce 404 -> exchange-service îl traduce în 400 cu mesaj clar,
    fără să înregistreze nimic în istoric."""

    async def fake_apply(*args, **kwargs):
        raise HTTPException(status_code=400, detail="Nu ai încă un cont pentru moneda asta.")

    monkeypatch.setattr("app.service._apply_exchange_in_accounts_service", fake_apply)

    response = await client.post(
        "/execute",
        json={"from_currency": "RON", "to_currency": "EUR", "amount_minor": 500_000},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 400

    mine = await client.get("/history", headers=AUTH_HEADER)
    assert mine.json() == []
