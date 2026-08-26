"""Teste pentru rutele de personal (routers/staff.py) — RequireStaff
(app/security.py) + revizuirea evaluărilor de fraud (app/fraud/staff.py).

fresh_database / clean_fraud_collections (conftest.py) se aplică automat,
la fel ca la restul testelor din acest director.
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

STAFF_USER_ID = str(ObjectId())
CUSTOMER_USER_ID = str(ObjectId())


def _make_token(user_id: str, role: str = "customer") -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "email": "test@example.com", "role": role, "iat": now, "exp": now + timedelta(minutes=30)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


STAFF_HEADER = {"Authorization": f"Bearer {_make_token(STAFF_USER_ID, role='staff')}"}
CUSTOMER_HEADER = {"Authorization": f"Bearer {_make_token(CUSTOMER_USER_ID, role='customer')}"}


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _seed_evaluation(**overrides) -> dict:
    base = {
        "transaction_id": ObjectId(),
        "user_id": CUSTOMER_USER_ID,
        "status": "ok",
        "score": 85,
        "fired_rules": [
            {
                "rule_id": "AMT-04",
                "family": "amount",
                "weight": 40,
                "contribution": 40.0,
                "excluded_from_score": False,
                "values": {"amount_minor": 99_000, "balance_minor": 100_000, "ratio": 0.98},
            }
        ],
        "decision_would_apply": "hold",
        "ruleset_version": "test-1",
        "shadow_mode": True,
        "evaluated_at": datetime.now(timezone.utc),
        "error": None,
        "created_at": datetime.now(timezone.utc),
    }
    base.update(overrides)
    result = await get_database().fraud_evaluations.insert_one(base)
    base["_id"] = result.inserted_id
    return base


# --- RequireStaff ------------------------------------------------------


async def test_require_staff_rejects_customer_jwt(client: AsyncClient):
    await _seed_evaluation()
    response = await client.get("/transactions/staff/fraud-evaluations", headers=CUSTOMER_HEADER)
    assert response.status_code == 403


async def test_require_staff_rejects_missing_jwt(client: AsyncClient):
    response = await client.get("/transactions/staff/fraud-evaluations")
    assert response.status_code == 401


async def test_require_staff_accepts_staff_jwt(client: AsyncClient):
    await _seed_evaluation()
    response = await client.get("/transactions/staff/fraud-evaluations", headers=STAFF_HEADER)
    assert response.status_code == 200


# --- Listare / filtre ---------------------------------------------------


async def test_list_returns_seeded_evaluations(client: AsyncClient):
    await _seed_evaluation(score=10, decision_would_apply="pass")
    await _seed_evaluation(score=90, decision_would_apply="hold")

    response = await client.get("/transactions/staff/fraud-evaluations", headers=STAFF_HEADER)
    assert response.status_code == 200
    assert len(response.json()) == 2


async def test_list_filters_by_decision_band(client: AsyncClient):
    await _seed_evaluation(score=10, decision_would_apply="pass")
    await _seed_evaluation(score=90, decision_would_apply="hold")

    response = await client.get("/transactions/staff/fraud-evaluations?decision_band=hold", headers=STAFF_HEADER)
    body = response.json()
    assert len(body) == 1
    assert body[0]["decision_would_apply"] == "hold"


async def test_list_filters_by_reviewed(client: AsyncClient):
    unreviewed = await _seed_evaluation()
    reviewed = await _seed_evaluation()
    await get_database().fraud_evaluations.update_one(
        {"_id": reviewed["_id"]},
        {
            "$set": {
                "review": {
                    "reviewed_by": STAFF_USER_ID,
                    "reviewed_at": datetime.now(timezone.utc),
                    "outcome": "legitimate",
                    "note": "",
                }
            }
        },
    )

    response = await client.get("/transactions/staff/fraud-evaluations?reviewed=false", headers=STAFF_HEADER)
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == str(unreviewed["_id"])


async def test_get_single_evaluation(client: AsyncClient):
    evaluation = await _seed_evaluation()
    response = await client.get(f"/transactions/staff/fraud-evaluations/{evaluation['_id']}", headers=STAFF_HEADER)
    assert response.status_code == 200
    assert response.json()["id"] == str(evaluation["_id"])


async def test_get_nonexistent_evaluation_404(client: AsyncClient):
    response = await client.get(f"/transactions/staff/fraud-evaluations/{ObjectId()}", headers=STAFF_HEADER)
    assert response.status_code == 404


# --- Revizuire -----------------------------------------------------------


async def test_review_writes_review_and_preserves_original_decision(client: AsyncClient):
    """Cel mai important test din acest fișier — garanția de integritate a
    auditului: revizuirea NU are voie să atingă decizia automată originală,
    doar să adauge o adnotare separată (aceeași filozofie ca testul
    "shadow mode nu poate strica un transfer" din Faza 1)."""
    evaluation = await _seed_evaluation()

    response = await client.patch(
        f"/transactions/staff/fraud-evaluations/{evaluation['_id']}/review",
        json={"outcome": "confirmed_fraud", "note": "Verificat cu userul, era fraudă."},
        headers=STAFF_HEADER,
    )
    assert response.status_code == 200
    body = response.json()

    assert body["review"]["outcome"] == "confirmed_fraud"
    assert body["review"]["reviewed_by"] == STAFF_USER_ID
    assert body["review"]["note"] == "Verificat cu userul, era fraudă."

    assert body["score"] == evaluation["score"]
    assert body["decision_would_apply"] == evaluation["decision_would_apply"]
    assert body["fired_rules"] == evaluation["fired_rules"]
    assert body["ruleset_version"] == evaluation["ruleset_version"]


async def test_review_twice_rejected_not_overwritten(client: AsyncClient):
    evaluation = await _seed_evaluation()

    first = await client.patch(
        f"/transactions/staff/fraud-evaluations/{evaluation['_id']}/review",
        json={"outcome": "confirmed_fraud", "note": "Prima opinie."},
        headers=STAFF_HEADER,
    )
    assert first.status_code == 200

    second = await client.patch(
        f"/transactions/staff/fraud-evaluations/{evaluation['_id']}/review",
        json={"outcome": "false_positive", "note": "A doua opinie."},
        headers=STAFF_HEADER,
    )
    assert second.status_code == 409

    stored = await get_database().fraud_evaluations.find_one({"_id": evaluation["_id"]})
    assert stored["review"]["outcome"] == "confirmed_fraud"  # neschimbat de a doua încercare


async def test_review_invalid_outcome_rejected(client: AsyncClient):
    evaluation = await _seed_evaluation()
    response = await client.patch(
        f"/transactions/staff/fraud-evaluations/{evaluation['_id']}/review",
        json={"outcome": "not-a-real-outcome", "note": ""},
        headers=STAFF_HEADER,
    )
    assert response.status_code == 422


async def test_review_nonexistent_evaluation_404(client: AsyncClient):
    response = await client.patch(
        f"/transactions/staff/fraud-evaluations/{ObjectId()}/review",
        json={"outcome": "legitimate", "note": ""},
        headers=STAFF_HEADER,
    )
    assert response.status_code == 404


async def test_review_requires_staff_role(client: AsyncClient):
    evaluation = await _seed_evaluation()
    response = await client.patch(
        f"/transactions/staff/fraud-evaluations/{evaluation['_id']}/review",
        json={"outcome": "legitimate", "note": ""},
        headers=CUSTOMER_HEADER,
    )
    assert response.status_code == 403


CUSTOMER_ACCOUNT_ID = str(ObjectId())
OTHER_SENDER_ACCOUNT_ID = str(ObjectId())


async def test_get_customer_transactions_shows_incomplete_incoming_transactions(client: AsyncClient, monkeypatch):
    """Spre deosebire de ruta normală a clientului (vezi test_transfers.py
    ::test_receiver_does_not_see_incoming_transaction_before_it_completes),
    personalul care investighează un client are nevoie de imaginea
    COMPLETĂ — inclusiv încercări primite care n-au ajuns la el (reținute
    pentru fraudă, eșuate, anulate) — vezi service.py::_build_filter_query,
    parametrul include_all_statuses."""

    async def fake_get_by_user(user_id: str) -> dict:
        return {
            "id": CUSTOMER_ACCOUNT_ID,
            "user_id": CUSTOMER_USER_ID,
            "iban": "RO11MAES0000000000000009",
            "currency": "RON",
            "balance_minor": 0,
            "status": "active",
        }

    monkeypatch.setattr("app.service._get_account_by_user", fake_get_by_user)

    db = get_database()
    await db.transactions.delete_many({})
    for seeded_status in ("pending_review", "failed", "cancelled", "completed"):
        await db.transactions.insert_one(
            {
                "from_account_id": OTHER_SENDER_ACCOUNT_ID,
                "to_account_id": CUSTOMER_ACCOUNT_ID,
                "from_iban": "RO22MAES0000000000000008",
                "to_iban": "RO11MAES0000000000000009",
                "amount_minor": 10_000,
                "currency": "RON",
                "description": "",
                "category": "other",
                "type": "transfer",
                "status": seeded_status,
                "recognized": False,
                "reported": False,
                "created_at": datetime.now(timezone.utc),
            }
        )

    response = await client.get(f"/transactions/staff/customers/{CUSTOMER_USER_ID}/transactions", headers=STAFF_HEADER)
    assert response.status_code == 200
    assert {item["status"] for item in response.json()} == {"pending_review", "failed", "cancelled", "completed"}

    await db.transactions.delete_many({})
