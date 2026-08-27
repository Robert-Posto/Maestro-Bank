"""Teste de integrare pentru refuzul direct BEN-04 (blocklist) — vezi
app/blocklist.py, app/service.py::create_transfer. Fișier auto-conținut,
la fel ca test_transfers_hold_integration.py (vezi acolo pentru motiv).

Blocklist-ul e SINGURA regulă din catalog care NU trece prin scoring —
verificăm explicit că ledger-ul (accounts-service) nu e atins deloc, nu
doar codul de status HTTP.
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from app import blocklist
from app.config import settings
from app.database import get_database
from app.main import app

pytestmark = pytest.mark.asyncio

USER_ID = str(ObjectId())
STAFF_USER_ID = str(ObjectId())
SOURCE_ACCOUNT_ID = str(ObjectId())
DEST_ACCOUNT_ID = str(ObjectId())
BLOCKED_IBAN = "RO99MAES0000000000000099"

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
    "iban": BLOCKED_IBAN,
    "currency": "RON",
    "balance_minor": 0,
    "status": "active",
}


def _make_token(user_id: str, role: str = "customer") -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "email": "test@example.com", "role": role, "iat": now, "exp": now + timedelta(minutes=5)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


AUTH_HEADER = {"Authorization": f"Bearer {_make_token(USER_ID)}"}
STAFF_HEADER = {"Authorization": f"Bearer {_make_token(STAFF_USER_ID, role='staff')}"}


@pytest.fixture(autouse=True)
async def clean_collections():
    db = get_database()
    await db.transactions.delete_many({})
    await db.beneficiary_blocklist.delete_many({})
    yield
    await db.transactions.delete_many({})
    await db.beneficiary_blocklist.delete_many({})


@pytest.fixture
def mock_ledger(monkeypatch):
    state = {"source": dict(SOURCE_ACCOUNT), "destination": dict(DEST_ACCOUNT), "transfer_calls": 0}

    async def fake_get_by_user(user_id: str) -> dict:
        return state["source"]

    async def fake_get_by_iban(iban: str):
        return state["destination"]

    async def fake_get_user_name(user_id: str) -> str | None:
        return None

    async def fake_apply_transfer(from_account_id: str, to_account_id: str, amount_minor: int) -> dict:
        state["transfer_calls"] += 1
        state["source"]["balance_minor"] -= amount_minor
        state["destination"]["balance_minor"] += amount_minor
        return {
            "from_balance_minor": state["source"]["balance_minor"],
            "to_balance_minor": state["destination"]["balance_minor"],
        }

    monkeypatch.setattr("app.service._get_account_by_user", fake_get_by_user)
    monkeypatch.setattr("app.service._get_account_by_iban", fake_get_by_iban)
    monkeypatch.setattr("app.service._get_user_name", fake_get_user_name)
    monkeypatch.setattr("app.service._apply_transfer", fake_apply_transfer)
    return state


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_transfer_to_blocked_iban_is_rejected_before_ledger(client: AsyncClient, mock_ledger):
    await blocklist.add_to_blocklist(iban=BLOCKED_IBAN, added_by=STAFF_USER_ID, reason="testat manual", source="manual")

    response = await client.post(
        "/transactions/transfers",
        json={"to_iban": BLOCKED_IBAN, "amount_minor": 10_000, "description": "", "category": "other"},
        headers=AUTH_HEADER,
    )

    assert response.status_code == 403
    assert mock_ledger["transfer_calls"] == 0  # accounts-service NICIODATĂ atins
    assert mock_ledger["source"]["balance_minor"] == 100_000
    assert mock_ledger["destination"]["balance_minor"] == 0

    stored = await get_database().transactions.find_one({"from_account_id": SOURCE_ACCOUNT_ID})
    assert stored is not None
    assert stored["status"] == "rejected"

    evaluation = await get_database().fraud_evaluations.find_one({"transaction_id": stored["_id"]})
    assert evaluation is not None
    assert evaluation["decision_would_apply"] == "reject"
    assert evaluation["score"] is None
    assert evaluation["fired_rules"] == []


async def test_transfer_to_non_blocked_iban_proceeds_normally(client: AsyncClient, mock_ledger, monkeypatch):
    # shadow_mode=True elimină orice nondeterminism legat de scor/hold —
    # aici testăm STRICT că absența unei intrări în blocklist nu blochează
    # nimic, nu comportamentul de scoring (deja acoperit în altă parte).
    monkeypatch.setattr("app.config.settings.fraud_shadow_mode", True)

    response = await client.post(
        "/transactions/transfers",
        json={"to_iban": BLOCKED_IBAN, "amount_minor": 10_000, "description": "", "category": "other"},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 201
    assert response.json()["status"] == "completed"
    assert mock_ledger["transfer_calls"] == 1


async def test_staff_can_add_list_and_remove_blocklist_entry(client: AsyncClient):
    create = await client.post(
        "/transactions/staff/blocklist", json={"iban": BLOCKED_IBAN, "reason": "intel extern"}, headers=STAFF_HEADER
    )
    assert create.status_code == 201
    entry = create.json()
    assert entry["iban"] == BLOCKED_IBAN
    assert entry["source"] == "manual"
    assert entry["added_by"] == STAFF_USER_ID

    listing = await client.get("/transactions/staff/blocklist", headers=STAFF_HEADER)
    assert listing.status_code == 200
    assert any(e["id"] == entry["id"] for e in listing.json())

    delete = await client.delete(f"/transactions/staff/blocklist/{entry['id']}", headers=STAFF_HEADER)
    assert delete.status_code == 204

    listing_after = await client.get("/transactions/staff/blocklist", headers=STAFF_HEADER)
    assert listing_after.json() == []


async def test_non_staff_cannot_manage_blocklist(client: AsyncClient):
    create = await client.post(
        "/transactions/staff/blocklist", json={"iban": BLOCKED_IBAN, "reason": "x"}, headers=AUTH_HEADER
    )
    assert create.status_code == 403

    listing = await client.get("/transactions/staff/blocklist", headers=AUTH_HEADER)
    assert listing.status_code == 403


async def test_adding_duplicate_iban_is_idempotent():
    first = await blocklist.add_to_blocklist(iban=BLOCKED_IBAN, added_by=STAFF_USER_ID, reason="a", source="manual")
    second = await blocklist.add_to_blocklist(iban=BLOCKED_IBAN, added_by=STAFF_USER_ID, reason="b", source="manual")

    assert first["_id"] == second["_id"]
    all_entries = await blocklist.list_blocklist()
    assert len(all_entries) == 1
    assert all_entries[0]["reason"] == "b"


async def test_confirmed_fraud_review_adds_transaction_beneficiary_to_blocklist(client: AsyncClient, mock_ledger):
    """Legătura automată — fraud/staff.py::review_evaluation. Nu re-testăm
    tot fluxul de scoring aici (vezi test_staff_fraud_review.py), doar că
    'confirmed_fraud' produce o intrare de blocklist pentru IBAN-ul real al
    tranzacției."""
    monkeypatch_iban = "RO55MAES0000000000000055"
    db = get_database()
    now = datetime.now(timezone.utc)
    tx_result = await db.transactions.insert_one(
        {
            "user_id": USER_ID,
            "from_account_id": SOURCE_ACCOUNT_ID,
            "to_account_id": DEST_ACCOUNT_ID,
            "to_iban": monkeypatch_iban,
            "amount_minor": 5_000,
            "currency": "RON",
            "description": "",
            "category": "other",
            "type": "transfer",
            "status": "completed",
            "recognized": False,
            "reported": False,
            "created_at": now,
        }
    )
    eval_result = await db.fraud_evaluations.insert_one(
        {
            "transaction_id": tx_result.inserted_id,
            "user_id": USER_ID,
            "status": "ok",
            "score": 90,
            "fired_rules": [],
            "decision_would_apply": "notify",
            "ruleset_version": "test",
            "shadow_mode": False,
            "evaluated_at": now,
            "error": None,
            "created_at": now,
        }
    )

    response = await client.patch(
        f"/transactions/staff/fraud-evaluations/{eval_result.inserted_id}/review",
        json={"outcome": "confirmed_fraud", "note": "cont compromis"},
        headers=STAFF_HEADER,
    )
    assert response.status_code == 200

    entry = await blocklist.is_blocked(monkeypatch_iban)
    assert entry is not None
    assert entry["source"] == "confirmed_fraud_review"
    assert entry["evaluation_id"] == eval_result.inserted_id
