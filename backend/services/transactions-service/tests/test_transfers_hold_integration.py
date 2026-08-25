"""Teste de integrare pentru fluxul REAL de reținere (hold), prin
POST /transactions/transfers + rutele de rezolvare — fișier auto-conținut,
la fel ca test_transfers_fraud.py (vezi acolo pentru motiv).

Simulează un ledger cu 3 conturi (sursă, reținere, destinație) prin
monkeypatch pe app.service (_get_account_by_user/_get_account_by_iban) ȘI
pe app.holds (_resolve_holding_account_id/_apply_ledger_transfer) — cele
două module au FIECARE propriile apeluri HTTP private către accounts-service,
mock-uite separat, dar mutând ACELAȘI dicționar de solduri, ca asserțiile
să rămână coerente pe tot fluxul (creare hold -> rezolvare).
"""

from datetime import datetime, timedelta, timezone

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
OTHER_USER_ID = str(ObjectId())
STAFF_USER_ID = str(ObjectId())
SOURCE_ACCOUNT_ID = str(ObjectId())
DEST_ACCOUNT_ID = str(ObjectId())
HOLDING_ACCOUNT_ID = str(ObjectId())

SOURCE_ACCOUNT = {
    "id": SOURCE_ACCOUNT_ID,
    "user_id": USER_ID,
    "iban": "RO11MAES0000000000000001",
    "currency": "RON",
    "balance_minor": 100_000,
    "status": "active",
}
DEST_ACCOUNT = {
    "id": DEST_ACCOUNT_ID,
    "user_id": str(ObjectId()),
    "iban": "RO22MAES0000000000000002",
    "currency": "RON",
    "balance_minor": 0,
    "status": "active",
}
OTHER_ACCOUNT = {
    "id": str(ObjectId()),
    "user_id": OTHER_USER_ID,
    "iban": "RO33MAES0000000000000003",
    "currency": "RON",
    "balance_minor": 50_000,
    "status": "active",
}


def _make_token(user_id: str, role: str = "customer") -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "email": "test@example.com", "role": role, "iat": now, "exp": now + timedelta(minutes=30)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


AUTH_HEADER = {"Authorization": f"Bearer {_make_token(USER_ID)}"}
OTHER_AUTH_HEADER = {"Authorization": f"Bearer {_make_token(OTHER_USER_ID)}"}
STAFF_HEADER = {"Authorization": f"Bearer {_make_token(STAFF_USER_ID, role='staff')}"}


@pytest.fixture(autouse=True)
async def clean_transactions():
    await get_database().transactions.delete_many({})
    yield
    await get_database().transactions.delete_many({})


@pytest.fixture
def mock_ledger(monkeypatch):
    """Ledger simulat cu 3 conturi (sursă/reținere/destinație) — vezi
    docstring-ul modulului."""
    state = {
        "source": dict(SOURCE_ACCOUNT),
        "destination": dict(DEST_ACCOUNT),
        "other": dict(OTHER_ACCOUNT),
        "holding_balance_minor": 0,
    }

    async def fake_get_by_user(user_id: str) -> dict:
        # Diferențiat pe user_id — necesar ca testele de izolare (userul B
        # nu poate anula hold-ul userului A) să chiar poată distinge cele
        # două conturi, nu doar să vadă mereu contul sursă.
        return state["other"] if user_id == OTHER_USER_ID else state["source"]

    async def fake_get_by_iban(iban: str):
        return state["destination"]

    async def fake_get_user_name(user_id: str) -> str | None:
        return None

    async def fake_apply_transfer(from_account_id: str, to_account_id: str, amount_minor: int) -> dict:
        # Calea NON-hold (shadow mode / bandă joasă) — trece prin
        # app.service._apply_transfer, NU prin holds.py.
        if state["source"]["balance_minor"] < amount_minor:
            raise HTTPException(status_code=409, detail="Sold insuficient.")
        state["source"]["balance_minor"] -= amount_minor
        state["destination"]["balance_minor"] += amount_minor
        return {"from_balance_minor": state["source"]["balance_minor"], "to_balance_minor": state["destination"]["balance_minor"]}

    async def fake_resolve_holding_account_id() -> str:
        return HOLDING_ACCOUNT_ID

    async def fake_apply_ledger_transfer(from_account_id: str, to_account_id: str, amount_minor: int) -> bool:
        if from_account_id == state["source"]["id"]:
            if state["source"]["balance_minor"] < amount_minor:
                return False
            state["source"]["balance_minor"] -= amount_minor
            state["holding_balance_minor"] += amount_minor
            return True
        if from_account_id == HOLDING_ACCOUNT_ID:
            if state["holding_balance_minor"] < amount_minor:
                return False
            state["holding_balance_minor"] -= amount_minor
            if to_account_id == state["destination"]["id"]:
                state["destination"]["balance_minor"] += amount_minor
            elif to_account_id == state["source"]["id"]:
                state["source"]["balance_minor"] += amount_minor
            return True
        return False

    async def fake_fetch_user_contact(user_id: str) -> dict:
        return {"first_name": "Test", "last_name": "User", "email": "test@example.com", "phone_number": "+40700000000"}

    monkeypatch.setattr("app.service._get_account_by_user", fake_get_by_user)
    monkeypatch.setattr("app.service._get_account_by_iban", fake_get_by_iban)
    monkeypatch.setattr("app.service._get_user_name", fake_get_user_name)
    monkeypatch.setattr("app.service._apply_transfer", fake_apply_transfer)
    monkeypatch.setattr("app.holds._resolve_holding_account_id", fake_resolve_holding_account_id)
    monkeypatch.setattr("app.holds._apply_ledger_transfer", fake_apply_ledger_transfer)
    monkeypatch.setattr("app.holds._fetch_user_contact", fake_fetch_user_contact)
    return state


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _trigger_hold(client: AsyncClient) -> dict:
    """99% din sold + beneficiar nou + categorie nouă -> scor >= 80,
    exact ca în Faza 1 (test_transfers_fraud.py) — reutilizat aici ca
    declanșator sigur pentru un hold."""
    response = await client.post(
        "/transactions/transfers",
        json={"to_iban": DEST_ACCOUNT["iban"], "amount_minor": 99_000, "description": "", "category": "groceries"},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 201
    return response.json()


async def test_high_score_transfer_creates_hold_not_completed(client: AsyncClient, mock_ledger):
    body = await _trigger_hold(client)

    assert body["status"] == "pending_review"
    assert body["hold"] is not None
    assert body["hold"]["expires_at"]
    assert mock_ledger["source"]["balance_minor"] == 1_000  # 100_000 - 99_000, banii CHIAR au ieșit
    assert mock_ledger["destination"]["balance_minor"] == 0  # NU au ajuns încă la beneficiar
    assert mock_ledger["holding_balance_minor"] == 99_000


async def test_shadow_mode_never_creates_a_hold(client: AsyncClient, mock_ledger, monkeypatch):
    """Regresie — Faza 1: cu fraud_shadow_mode=True, ACELAȘI transfer de
    risc trebuie să treacă normal, fără reținere."""
    monkeypatch.setattr("app.config.settings.fraud_shadow_mode", True)

    response = await client.post(
        "/transactions/transfers",
        json={"to_iban": DEST_ACCOUNT["iban"], "amount_minor": 99_000, "description": "", "category": "groceries"},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert body["hold"] is None
    assert mock_ledger["destination"]["balance_minor"] == 99_000


async def test_customer_can_cancel_own_hold(client: AsyncClient, mock_ledger):
    held = await _trigger_hold(client)

    response = await client.post(f"/transactions/{held['id']}/hold/cancel", headers=AUTH_HEADER)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["hold"]["resolution"] == "cancelled"
    assert mock_ledger["source"]["balance_minor"] == 100_000  # revenit integral
    assert mock_ledger["holding_balance_minor"] == 0


async def test_customer_cannot_cancel_someone_elses_hold(client: AsyncClient, mock_ledger):
    held = await _trigger_hold(client)

    response = await client.post(f"/transactions/{held['id']}/hold/cancel", headers=OTHER_AUTH_HEADER)
    assert response.status_code == 404
    # neatins
    stored = await get_database().transactions.find_one({"_id": ObjectId(held["id"])})
    assert stored["status"] == "pending_review"


async def test_staff_can_approve_hold(client: AsyncClient, mock_ledger):
    held = await _trigger_hold(client)

    response = await client.post(f"/transactions/staff/holds/{held['id']}/approve", headers=STAFF_HEADER)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["resolution"] == "released"
    assert mock_ledger["destination"]["balance_minor"] == 99_000
    assert mock_ledger["holding_balance_minor"] == 0


async def test_staff_can_reject_hold(client: AsyncClient, mock_ledger):
    held = await _trigger_hold(client)

    response = await client.post(f"/transactions/staff/holds/{held['id']}/reject", headers=STAFF_HEADER)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["resolution"] == "cancelled"
    assert mock_ledger["source"]["balance_minor"] == 100_000
    assert mock_ledger["destination"]["balance_minor"] == 0


async def test_non_staff_cannot_approve_or_reject(client: AsyncClient, mock_ledger):
    held = await _trigger_hold(client)

    approve = await client.post(f"/transactions/staff/holds/{held['id']}/approve", headers=AUTH_HEADER)
    reject = await client.post(f"/transactions/staff/holds/{held['id']}/reject", headers=AUTH_HEADER)
    assert approve.status_code == 403
    assert reject.status_code == 403


async def test_staff_holds_list_shows_pending_hold_with_score_and_contact(client: AsyncClient, mock_ledger):
    held = await _trigger_hold(client)

    response = await client.get("/transactions/staff/holds", headers=STAFF_HEADER)
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == held["id"]
    assert body[0]["score"] is not None
    assert body[0]["score"] >= 80
    assert body[0]["customer"]["phone_number"] == "+40700000000"


async def test_staff_holds_list_excludes_resolved_holds(client: AsyncClient, mock_ledger):
    held = await _trigger_hold(client)
    await client.post(f"/transactions/staff/holds/{held['id']}/approve", headers=STAFF_HEADER)

    response = await client.get("/transactions/staff/holds", headers=STAFF_HEADER)
    assert response.json() == []
