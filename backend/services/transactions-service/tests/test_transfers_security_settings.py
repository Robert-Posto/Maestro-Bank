"""
Teste pentru "Security settings" (Cardul meu) — Payment confirmation
(PIN-ul cardului la transferuri peste prag) și Transaction alerts
(notificare la fiecare tranzacție) — vezi app/service.py::
_get_account_card_settings / _verify_card_pin / _PAYMENT_CONFIRMATION_THRESHOLD_MINOR.

_get_account_card_settings și _verify_card_pin (apeluri către
accounts-service) sunt MOCK-uite aici, la fel ca restul apelurilor
cross-service — vezi antetul test_transfers.py.

Rulare: vezi antetul test_transfers.py.
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from app import service as service_module
from app.config import settings
from app.database import get_database
from app.main import app

pytestmark = pytest.mark.asyncio

USER_ID = str(ObjectId())
SOURCE_ACCOUNT_ID = str(ObjectId())
DEST_ACCOUNT_ID = str(ObjectId())
DEST_USER_ID = str(ObjectId())
CARD_ID = str(ObjectId())

SOURCE_ACCOUNT = {
    "id": SOURCE_ACCOUNT_ID,
    "user_id": USER_ID,
    "iban": "RO11MAES0000000000000001",
    "currency": "RON",
    "balance_minor": 10_000_000,  # 100.000 RON — suficient pentru orice test de aici
    "status": "active",
}

DEST_ACCOUNT = {
    "id": DEST_ACCOUNT_ID,
    "user_id": DEST_USER_ID,
    "iban": "RO22MAES0000000000000002",
    "currency": "RON",
    "balance_minor": 0,
    "status": "active",
}

# Peste pragul de 5.000,00 RON (500_000 bani) — vezi
# service.py::_PAYMENT_CONFIRMATION_THRESHOLD_MINOR.
LARGE_AMOUNT_MINOR = 600_000
SMALL_AMOUNT_MINOR = 10_000


def _make_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "email": "test@example.com", "iat": now, "exp": now + timedelta(minutes=5)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


AUTH_HEADER = {"Authorization": f"Bearer {_make_token(USER_ID)}"}


@pytest.fixture(autouse=True)
async def clean_transactions():
    await get_database().transactions.delete_many({})
    yield
    await get_database().transactions.delete_many({})


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_accounts(monkeypatch):
    state = {"source": dict(SOURCE_ACCOUNT), "destination": dict(DEST_ACCOUNT)}
    # {account_id: {"transaction_alerts_enabled": bool, "payment_confirmation_required": bool, "payment_confirmation_card_id": str | None}}
    card_settings: dict[str, dict] = {
        SOURCE_ACCOUNT_ID: {
            "transaction_alerts_enabled": True,
            "payment_confirmation_required": False,
            "payment_confirmation_card_id": None,
        },
        DEST_ACCOUNT_ID: {
            "transaction_alerts_enabled": True,
            "payment_confirmation_required": False,
            "payment_confirmation_card_id": None,
        },
    }
    notifications: list[tuple[str, str, str]] = []

    async def fake_get_by_user(user_id: str) -> dict:
        return state["source"] if user_id == USER_ID else state["destination"]

    async def fake_get_by_iban(iban: str):
        return state["destination"]

    async def fake_apply_transfer(from_id: str, to_id: str, amount_minor: int) -> dict:
        state["source"]["balance_minor"] -= amount_minor
        state["destination"]["balance_minor"] += amount_minor
        return {"from_balance_minor": state["source"]["balance_minor"], "to_balance_minor": state["destination"]["balance_minor"]}

    async def fake_get_user_name(user_id: str) -> str | None:
        return {USER_ID: "Octavia Stefan", DEST_USER_ID: "Andrei Popescu"}.get(user_id)

    async def fake_get_account_card_settings(account_id: str) -> dict:
        return card_settings[account_id]

    async def fake_verify_card_pin(card_id: str, pin: str) -> bool:
        return card_id == CARD_ID and pin == "1234"

    async def fake_notify_user(user_id: str, kind: str, text: str) -> None:
        notifications.append((user_id, kind, text))

    monkeypatch.setattr("app.service._get_account_by_user", fake_get_by_user)
    monkeypatch.setattr("app.service._get_account_by_iban", fake_get_by_iban)
    monkeypatch.setattr("app.service._apply_transfer", fake_apply_transfer)
    monkeypatch.setattr("app.service._get_user_name", fake_get_user_name)
    monkeypatch.setattr("app.service._get_account_card_settings", fake_get_account_card_settings)
    monkeypatch.setattr("app.service._verify_card_pin", fake_verify_card_pin)
    monkeypatch.setattr("app.service._notify_user", fake_notify_user)

    return {"state": state, "card_settings": card_settings, "notifications": notifications}


async def _make_transfer(client: AsyncClient, amount_minor: int, card_pin: str | None = None):
    payload = {"to_iban": DEST_ACCOUNT["iban"], "amount_minor": amount_minor, "description": "test"}
    if card_pin is not None:
        payload["card_pin"] = card_pin
    return await client.post("/transactions/transfers", json=payload, headers=AUTH_HEADER)


# --- Payment confirmation ----------------------------------------------------


async def test_transfer_under_threshold_never_requires_pin(client: AsyncClient, mock_accounts):
    mock_accounts["card_settings"][SOURCE_ACCOUNT_ID]["payment_confirmation_required"] = True
    mock_accounts["card_settings"][SOURCE_ACCOUNT_ID]["payment_confirmation_card_id"] = CARD_ID

    response = await _make_transfer(client, SMALL_AMOUNT_MINOR)
    assert response.status_code == 201


async def test_transfer_over_threshold_without_confirmation_enabled_succeeds(client: AsyncClient, mock_accounts):
    # payment_confirmation_required rămâne False (implicit) — cardul n-are controlul activat.
    response = await _make_transfer(client, LARGE_AMOUNT_MINOR)
    assert response.status_code == 201


async def test_transfer_over_threshold_with_confirmation_enabled_requires_pin(client: AsyncClient, mock_accounts):
    mock_accounts["card_settings"][SOURCE_ACCOUNT_ID]["payment_confirmation_required"] = True
    mock_accounts["card_settings"][SOURCE_ACCOUNT_ID]["payment_confirmation_card_id"] = CARD_ID

    response = await _make_transfer(client, LARGE_AMOUNT_MINOR)  # fără card_pin
    assert response.status_code == 428
    # NU s-a creat nicio tranzacție (nici măcar "failed") — respins ÎNAINTE de insert.
    assert await get_database().transactions.count_documents({}) == 0


async def test_transfer_over_threshold_with_wrong_pin_rejected(client: AsyncClient, mock_accounts):
    mock_accounts["card_settings"][SOURCE_ACCOUNT_ID]["payment_confirmation_required"] = True
    mock_accounts["card_settings"][SOURCE_ACCOUNT_ID]["payment_confirmation_card_id"] = CARD_ID

    response = await _make_transfer(client, LARGE_AMOUNT_MINOR, card_pin="0000")
    assert response.status_code == 401
    assert await get_database().transactions.count_documents({}) == 0


async def test_transfer_over_threshold_with_correct_pin_succeeds(client: AsyncClient, mock_accounts):
    mock_accounts["card_settings"][SOURCE_ACCOUNT_ID]["payment_confirmation_required"] = True
    mock_accounts["card_settings"][SOURCE_ACCOUNT_ID]["payment_confirmation_card_id"] = CARD_ID

    response = await _make_transfer(client, LARGE_AMOUNT_MINOR, card_pin="1234")
    assert response.status_code == 201
    assert response.json()["status"] == "completed"


# --- Transaction alerts --------------------------------------------------------


async def test_sender_notified_when_alerts_enabled(client: AsyncClient, mock_accounts):
    response = await _make_transfer(client, SMALL_AMOUNT_MINOR)
    assert response.status_code == 201
    kinds = [n[1] for n in mock_accounts["notifications"] if n[0] == USER_ID]
    assert "transfer" in kinds


async def test_sender_not_notified_when_alerts_disabled(client: AsyncClient, mock_accounts):
    mock_accounts["card_settings"][SOURCE_ACCOUNT_ID]["transaction_alerts_enabled"] = False

    response = await _make_transfer(client, SMALL_AMOUNT_MINOR)
    assert response.status_code == 201
    sender_notifications = [n for n in mock_accounts["notifications"] if n[0] == USER_ID]
    assert sender_notifications == []


async def test_receiver_alerts_gated_independently_from_sender(client: AsyncClient, mock_accounts):
    """Alertele expeditorului OPRITE, ale destinatarului PORNITE — fiecare
    parte primește notificare doar dacă ȘI-A activat propriile alerte, nu
    în funcție de setarea celeilalte părți."""
    mock_accounts["card_settings"][SOURCE_ACCOUNT_ID]["transaction_alerts_enabled"] = False
    mock_accounts["card_settings"][DEST_ACCOUNT_ID]["transaction_alerts_enabled"] = True

    response = await _make_transfer(client, SMALL_AMOUNT_MINOR)
    assert response.status_code == 201

    sender_notifications = [n for n in mock_accounts["notifications"] if n[0] == USER_ID]
    receiver_notifications = [n for n in mock_accounts["notifications"] if n[0] == DEST_USER_ID]
    assert sender_notifications == []
    assert any(n[1] == "transfer_received" for n in receiver_notifications)


async def test_accounts_service_unavailable_degrades_to_alerts_on_confirmation_off(client: AsyncClient, monkeypatch, mock_accounts):
    """Dacă accounts-service e indisponibil, _get_account_card_settings
    (funcția REALĂ, nu mock-ul din fixture) cade pe implicit: alerte ACTIVE
    (nu lăsăm userul brusc fără notificări), confirmare DEZACTIVATĂ (nu
    blocăm un transfer normal doar pentru un serviciu extern jos)."""

    async def fake_get_by_user(user_id: str) -> dict:
        return mock_accounts["state"]["source"]

    monkeypatch.setattr("app.service._get_account_by_user", fake_get_by_user)
    # Restaurăm funcția REALĂ (nu mock-ul din fixture) — vrem să testăm
    # chiar degradarea ei la eroare de rețea.
    monkeypatch.setattr("app.service._get_account_card_settings", service_module._get_account_card_settings)
    monkeypatch.setattr("app.config.settings.accounts_service_url", "http://accounts-service-nu-exista:9999")

    response = await _make_transfer(client, LARGE_AMOUNT_MINOR)
    assert response.status_code == 201  # NU 428 — degradare grațioasă
