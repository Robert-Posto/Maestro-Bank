"""Teste de integrare pentru loans-service — apelurile către accounts-service
și eligibility sunt MOCK-uite, la fel ca la deposits-service/investments-service.

Rulare (cu stack-ul pornit prin `docker compose up`, bază de TEST separată):

    docker compose exec loans-service pip install pytest==8.3.3 pytest-asyncio==0.24.0 httpx==0.27.2 -q
    docker compose exec -e MONGO_URL=mongodb://mongodb:27017/loans_db_test loans-service python -m pytest -q
"""

from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from app.database import get_database
from app.eligibility import EligibilityResult
from app.main import app
from app.models import LoanApplyRequest

USER_ID = str(ObjectId())
CURRENT_ACCOUNT_ID = str(ObjectId())


@pytest.fixture(autouse=True)
async def clean_collections():
    db = get_database()
    await db.loans.delete_many({})
    await db.loan_payments.delete_many({})
    yield
    await db.loans.delete_many({})
    await db.loan_payments.delete_many({})


@pytest.fixture
def mock_accounts(monkeypatch):
    state = {"balance_minor": 10_000_000, "debits": [], "credits": []}

    async def fake_get_current_account(user_id: str) -> dict:
        return {
            "id": CURRENT_ACCOUNT_ID,
            "iban": "RO_CURRENT",
            "currency": "RON",
            "balance_minor": state["balance_minor"],
            "status": "active",
            "account_type": "current",
        }

    async def fake_debit(account_id: str, amount_minor: int) -> bool:
        assert account_id == CURRENT_ACCOUNT_ID
        if amount_minor > state["balance_minor"]:
            return False
        state["balance_minor"] -= amount_minor
        state["debits"].append(amount_minor)
        return True

    async def fake_credit(account_id: str, amount_minor: int) -> None:
        assert account_id == CURRENT_ACCOUNT_ID
        state["balance_minor"] += amount_minor
        state["credits"].append(amount_minor)

    monkeypatch.setattr("app.service._get_current_account", fake_get_current_account)
    monkeypatch.setattr("app.service._debit_account", fake_debit)
    monkeypatch.setattr("app.service._credit_account", fake_credit)
    return state


@pytest.fixture
def mock_notify(monkeypatch):
    calls = []

    async def fake_notify(
        user_id: str, kind: str, message_key: str, message_params: dict | None = None, reference_id: str | None = None
    ) -> None:
        calls.append(
            {
                "user_id": user_id,
                "kind": kind,
                "message_key": message_key,
                "message_params": message_params,
                "reference_id": reference_id,
            }
        )

    monkeypatch.setattr("app.service._notify_user", fake_notify)
    return calls


def _mock_eligible(monkeypatch, max_affordable_installment_minor: int = 10_000_000):
    async def fake_evaluate(user_id: str, existing_installments_minor: int) -> EligibilityResult:
        return EligibilityResult(
            average_monthly_income_minor=max_affordable_installment_minor * 3,
            max_affordable_installment_minor=max_affordable_installment_minor,
            existing_installments_minor=existing_installments_minor,
        )

    monkeypatch.setattr("app.service.evaluate_eligibility", fake_evaluate)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --- Cerere de credit ---------------------------------------------------------


async def test_apply_for_loan_approves_and_credits_when_eligible(monkeypatch, mock_accounts, mock_notify):
    from app.service import apply_for_loan

    _mock_eligible(monkeypatch)
    loan = await apply_for_loan(USER_ID, LoanApplyRequest(amount_minor=1_000_000, term_months=12))

    assert loan.status == "active"
    assert loan.principal_minor == 1_000_000
    assert loan.outstanding_principal_minor == 1_000_000
    assert loan.payments_made == 0
    assert loan.monthly_installment_minor > 0
    assert mock_accounts["credits"] == [1_000_000]
    assert any(call["kind"] == "loan_approved" for call in mock_notify)


async def test_apply_for_loan_rejects_amount_below_minimum(mock_accounts, mock_notify):
    from app.service import apply_for_loan

    with pytest.raises(Exception) as exc_info:
        await apply_for_loan(USER_ID, LoanApplyRequest(amount_minor=1_000, term_months=12))
    assert exc_info.value.status_code == 400


async def test_apply_for_loan_rejects_when_installment_exceeds_income(monkeypatch, mock_accounts, mock_notify):
    from app.service import apply_for_loan

    _mock_eligible(monkeypatch, max_affordable_installment_minor=0)
    with pytest.raises(Exception) as exc_info:
        await apply_for_loan(USER_ID, LoanApplyRequest(amount_minor=1_000_000, term_months=12))
    assert exc_info.value.status_code == 422
    assert mock_accounts["credits"] == []  # nu s-a mutat niciun ban


async def test_apply_for_loan_counts_existing_active_loans_toward_eligibility(monkeypatch, mock_accounts, mock_notify):
    from app.service import apply_for_loan

    captured: dict = {}

    async def fake_evaluate(user_id: str, existing_installments_minor: int) -> EligibilityResult:
        captured["existing"] = existing_installments_minor
        return EligibilityResult(
            average_monthly_income_minor=10_000_000,
            max_affordable_installment_minor=10_000_000,
            existing_installments_minor=existing_installments_minor,
        )

    monkeypatch.setattr("app.service.evaluate_eligibility", fake_evaluate)

    await get_database().loans.insert_one(
        {
            "user_id": USER_ID,
            "account_id": CURRENT_ACCOUNT_ID,
            "principal_minor": 500_000,
            "outstanding_principal_minor": 400_000,
            "term_months": 12,
            "rate_percent_annual": 9.5,
            "monthly_installment_minor": 43_800,
            "payments_made": 2,
            "missed_payments_count": 0,
            "opened_at": datetime.now(timezone.utc),
            "next_payment_due_at": datetime.now(timezone.utc) + timedelta(days=10),
            "status": "active",
            "paid_off_at": None,
        }
    )

    await apply_for_loan(USER_ID, LoanApplyRequest(amount_minor=1_000_000, term_months=12))
    assert captured["existing"] == 43_800


# --- Plată anticipată -----------------------------------------------------------


async def test_payoff_loan_debits_outstanding_and_closes(monkeypatch, mock_accounts, mock_notify):
    from app.service import apply_for_loan, payoff_loan

    _mock_eligible(monkeypatch)
    loan = await apply_for_loan(USER_ID, LoanApplyRequest(amount_minor=1_000_000, term_months=12))
    debits_before = list(mock_accounts["debits"])

    result = await payoff_loan(loan.id, USER_ID)

    assert result.status == "paid_off"
    assert result.outstanding_principal_minor == 0
    assert mock_accounts["debits"] == debits_before + [1_000_000]
    assert any(call["kind"] == "loan_paid_off" for call in mock_notify)


async def test_payoff_loan_rejects_insufficient_funds(monkeypatch, mock_accounts, mock_notify):
    from app.service import apply_for_loan, payoff_loan

    _mock_eligible(monkeypatch)
    loan = await apply_for_loan(USER_ID, LoanApplyRequest(amount_minor=1_000_000, term_months=12))
    mock_accounts["balance_minor"] = 0  # fondurile "dispar" înainte de plata anticipată

    with pytest.raises(Exception) as exc_info:
        await payoff_loan(loan.id, USER_ID)
    assert exc_info.value.status_code == 409


async def test_payoff_loan_rejects_unknown_loan(mock_accounts, mock_notify):
    from app.service import payoff_loan

    with pytest.raises(Exception) as exc_info:
        await payoff_loan(str(ObjectId()), USER_ID)
    assert exc_info.value.status_code == 404


# --- Rate automate (scheduler) ---------------------------------------------------


async def test_process_due_payments_pays_installment_and_advances_schedule(monkeypatch, mock_accounts, mock_notify):
    from app.service import apply_for_loan, process_due_payments

    _mock_eligible(monkeypatch)
    loan = await apply_for_loan(USER_ID, LoanApplyRequest(amount_minor=1_000_000, term_months=12))
    await get_database().loans.update_one(
        {"_id": ObjectId(loan.id)}, {"$set": {"next_payment_due_at": datetime.now(timezone.utc) - timedelta(days=1)}}
    )

    processed = await process_due_payments()
    assert processed == 1

    doc = await get_database().loans.find_one({"_id": ObjectId(loan.id)})
    assert doc["payments_made"] == 1
    assert doc["outstanding_principal_minor"] < loan.principal_minor
    # Mongo/Motor întoarce datetime-uri NAIVE (fără tzinfo) la citire, deși
    # au fost scrise ca aware (UTC) — normalizăm înainte de comparat.
    next_due = doc["next_payment_due_at"].replace(tzinfo=timezone.utc)
    assert next_due > datetime.now(timezone.utc) + timedelta(days=20)

    payments = await get_database().loan_payments.find({"loan_id": loan.id}).to_list(length=10)
    assert len(payments) == 1
    assert payments[0]["principal_portion_minor"] + payments[0]["interest_portion_minor"] == payments[0]["amount_minor"]


async def test_process_due_payments_closes_loan_on_final_installment(monkeypatch, mock_accounts, mock_notify):
    from app.service import process_due_payments

    await get_database().loans.insert_one(
        {
            "user_id": USER_ID,
            "account_id": CURRENT_ACCOUNT_ID,
            "principal_minor": 1_000_000,
            "outstanding_principal_minor": 50_000,  # ultima felie mică, cu rest de rotunjire
            "term_months": 12,
            "rate_percent_annual": 9.5,
            "monthly_installment_minor": 87_600,
            "payments_made": 11,  # a 12-a rată = ultima
            "missed_payments_count": 0,
            "opened_at": datetime.now(timezone.utc) - timedelta(days=330),
            "next_payment_due_at": datetime.now(timezone.utc) - timedelta(days=1),
            "status": "active",
            "paid_off_at": None,
        }
    )

    processed = await process_due_payments()
    assert processed == 1

    doc = await get_database().loans.find_one({"user_id": USER_ID})
    assert doc["status"] == "paid_off"
    assert doc["outstanding_principal_minor"] == 0
    assert doc["next_payment_due_at"] is None
    assert any(call["kind"] == "loan_paid_off" for call in mock_notify)


async def test_process_due_payments_retries_after_insufficient_funds(monkeypatch, mock_accounts, mock_notify):
    from app.service import apply_for_loan, process_due_payments

    _mock_eligible(monkeypatch)
    loan = await apply_for_loan(USER_ID, LoanApplyRequest(amount_minor=1_000_000, term_months=12))
    await get_database().loans.update_one(
        {"_id": ObjectId(loan.id)}, {"$set": {"next_payment_due_at": datetime.now(timezone.utc) - timedelta(days=1)}}
    )
    mock_accounts["balance_minor"] = 0  # sold insuficient pt rată

    processed = await process_due_payments()
    assert processed == 1

    doc = await get_database().loans.find_one({"_id": ObjectId(loan.id)})
    assert doc["status"] == "active"  # nu s-a închis, nu s-a penalizat, doar reîncearcă
    assert doc["payments_made"] == 0
    assert doc["missed_payments_count"] == 1
    next_due = doc["next_payment_due_at"].replace(tzinfo=timezone.utc)
    assert next_due < datetime.now(timezone.utc) + timedelta(days=2)
    assert any(call["kind"] == "loan_payment_missed" for call in mock_notify)


# --- Endpoint HTTP -----------------------------------------------------------------


async def test_apply_endpoint_requires_auth(client: AsyncClient):
    response = await client.post("/loans/apply", json={"amount_minor": 100_000, "term_months": 12})
    assert response.status_code == 401
