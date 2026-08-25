"""
Teste pentru PIN de card (creare + reveal) — vezi app/pin.py,
app/service.py::create_card/reveal_card/backfill_missing_card_pins.

Rulare: vezi antetul test_accounts.py.
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

import app.service as service_module
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


async def _provision(client: AsyncClient) -> tuple[str, dict, dict]:
    user_id = str(ObjectId())
    response = await client.post("/internal/accounts/provision", json={"user_id": user_id})
    assert response.status_code == 201
    body = response.json()
    card = body["card"]
    # /internal/accounts/provision serializează cu alias-ul Mongo ("_id"),
    # spre deosebire de POST /cards (public, response_model_by_alias=False,
    # vezi routers/cards.py) — normalizăm aici ca restul testelor să poată
    # folosi mereu card["id"], indiferent prin ce rută a fost obținut cardul.
    card["id"] = card.get("id") or card["_id"]
    return user_id, {"Authorization": f"Bearer {_make_token(user_id)}"}, card


async def test_create_card_requires_pin(client: AsyncClient):
    _, headers, _ = await _provision(client)
    response = await client.post("/cards", json={"design": "midnight", "type": "virtual"}, headers=headers)
    assert response.status_code == 422


async def test_create_card_rejects_non_numeric_pin(client: AsyncClient):
    _, headers, _ = await _provision(client)
    response = await client.post(
        "/cards", json={"design": "midnight", "type": "virtual", "pin": "12ab"}, headers=headers
    )
    assert response.status_code == 422


async def test_create_card_rejects_wrong_length_pin(client: AsyncClient):
    _, headers, _ = await _provision(client)
    response = await client.post(
        "/cards", json={"design": "midnight", "type": "virtual", "pin": "123"}, headers=headers
    )
    assert response.status_code == 422


async def test_create_card_succeeds_and_does_not_leak_pin(client: AsyncClient):
    _, headers, _ = await _provision(client)
    response = await client.post(
        "/cards", json={"design": "aurora", "type": "virtual", "pin": "4321"}, headers=headers
    )
    assert response.status_code == 201
    body = response.json()
    assert "pin" not in body
    assert "pin_hash" not in body


async def test_reveal_card_with_correct_pin(client: AsyncClient):
    user_id, headers, _ = await _provision(client)
    created = (
        await client.post("/cards", json={"design": "midnight", "type": "virtual", "pin": "1234"}, headers=headers)
    ).json()

    response = await client.post(f"/cards/{created['id']}/reveal", json={"pin": "1234"}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body["pan"]) == 16
    assert len(body["cvv"]) == 3


async def test_reveal_card_with_wrong_pin(client: AsyncClient):
    _, headers, _ = await _provision(client)
    created = (
        await client.post("/cards", json={"design": "midnight", "type": "virtual", "pin": "1234"}, headers=headers)
    ).json()

    response = await client.post(f"/cards/{created['id']}/reveal", json={"pin": "9999"}, headers=headers)
    assert response.status_code == 401
    assert response.json()["detail"] == "PIN incorect."


async def test_reveal_card_requires_pin_or_webauthn(client: AsyncClient):
    _, headers, card = await _provision(client)
    response = await client.post(f"/cards/{card['id']}/reveal", json={}, headers=headers)
    assert response.status_code == 422


async def test_reveal_card_rejects_both_pin_and_webauthn(client: AsyncClient):
    _, headers, card = await _provision(client)
    response = await client.post(
        f"/cards/{card['id']}/reveal",
        json={"pin": "1234", "webauthn_challenge_id": "x", "webauthn_assertion": {}},
        headers=headers,
    )
    assert response.status_code == 422


async def test_backfill_generates_pin_for_legacy_card(client: AsyncClient, monkeypatch):
    """Cardul provizionat automat la înregistrare (vezi _provision) — la
    fel ca orice card creat ÎNAINTE de introducerea PIN-ului — nu are
    pin_hash până la backfill (POST /internal/accounts/provision nu cere
    un PIN, e apelat de auth-service la înregistrare, fără intervenție
    umană posibilă acolo)."""
    _, headers, card = await _provision(client)

    db = get_database()
    doc_before = await db.cards.find_one({"_id": ObjectId(card["id"])})
    assert "pin_hash" not in doc_before

    monkeypatch.setattr(service_module.pin_module, "generate_random_pin", lambda: "5555")
    await service_module.backfill_missing_card_pins()

    response = await client.post(f"/cards/{card['id']}/reveal", json={"pin": "5555"}, headers=headers)
    assert response.status_code == 200


async def test_backfill_is_idempotent(client: AsyncClient):
    """A doua rulare nu suprascrie PIN-uri deja setate — altfel un PIN ales
    de user la creare ar putea fi înlocuit tăcut la un restart al serviciului."""
    _, headers, _ = await _provision(client)
    created = (
        await client.post("/cards", json={"design": "midnight", "type": "virtual", "pin": "1234"}, headers=headers)
    ).json()

    await service_module.backfill_missing_card_pins()

    response = await client.post(f"/cards/{created['id']}/reveal", json={"pin": "1234"}, headers=headers)
    assert response.status_code == 200
