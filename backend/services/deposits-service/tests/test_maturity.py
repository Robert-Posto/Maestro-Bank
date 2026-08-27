"""Teste pentru maturarea depozitelor (reînnoire automată SAU plată în
cont, în funcție de renew_at_maturity) — vezi app/service.py::
process_matured_deposits, apelat periodic de app/scheduler.py::maturity_loop.
"""

from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId

from app.database import get_database
from app.models import DepositOpenRequest

USER_ID = str(ObjectId())


@pytest.fixture(autouse=True)
async def clean_deposits():
    await get_database().deposits.delete_many({})
    yield
    await get_database().deposits.delete_many({})


@pytest.fixture
def mock_accounts(monkeypatch):
    state = {"balance_minor": 500_000}

    async def fake_get_account(user_id: str, account_type: str) -> dict:
        return {"id": "acc1", "iban": "RO_X", "currency": "RON", "balance_minor": state["balance_minor"], "status": "active", "account_type": "current"}

    async def fake_debit(account_id: str, amount_minor: int) -> None:
        state["balance_minor"] -= amount_minor

    async def fake_credit(account_id: str, amount_minor: int) -> None:
        state["balance_minor"] += amount_minor

    monkeypatch.setattr("app.service._get_account_by_user_and_type", fake_get_account)
    monkeypatch.setattr("app.service._debit_account", fake_debit)
    monkeypatch.setattr("app.service._credit_account", fake_credit)
    return state


async def _open_deposit_with_past_maturity(renew: bool) -> str:
    """Deschide un depozit prin fluxul normal, apoi forțează matures_at în
    trecut direct în DB — mai simplu decât să aștepți luni în test."""
    from app.service import open_deposit

    deposit = await open_deposit(
        USER_ID, DepositOpenRequest(currency="RON", term_months=12, amount_minor=100_000, renew_at_maturity=renew)
    )
    await get_database().deposits.update_one(
        {"_id": ObjectId(deposit.id)},
        {"$set": {"matures_at": datetime.now(timezone.utc) - timedelta(days=1)}},
    )
    return deposit.id


async def test_matured_deposit_with_renew_creates_new_deposit(mock_accounts):
    from app.service import process_matured_deposits

    old_id = await _open_deposit_with_past_maturity(renew=True)
    processed = await process_matured_deposits()
    assert processed == 1

    old_doc = await get_database().deposits.find_one({"_id": ObjectId(old_id)})
    assert old_doc["status"] == "matured_renewed"
    assert old_doc["renewed_into_deposit_id"] is not None

    new_doc = await get_database().deposits.find_one({"_id": ObjectId(old_doc["renewed_into_deposit_id"])})
    assert new_doc["status"] == "active"
    # principal nou = principal vechi (100.000) + dobânda (100.000 * 5.75% * 1) = 105.750
    assert new_doc["principal_minor"] == 105_750
    assert new_doc["renewed_from_deposit_id"] == old_id


async def test_matured_deposit_without_renew_pays_out_to_account(mock_accounts):
    from app.service import process_matured_deposits

    deposit_id = await _open_deposit_with_past_maturity(renew=False)
    balance_before = mock_accounts["balance_minor"]  # deja debitat 100.000 la deschidere

    processed = await process_matured_deposits()
    assert processed == 1

    doc = await get_database().deposits.find_one({"_id": ObjectId(deposit_id)})
    assert doc["status"] == "closed_paid_out"
    # principal (100.000) + dobânda (5.750) revin în cont
    assert mock_accounts["balance_minor"] == balance_before + 105_750


async def test_process_matured_deposits_ignores_deposits_not_yet_due(mock_accounts):
    from app.service import open_deposit, process_matured_deposits

    await open_deposit(USER_ID, DepositOpenRequest(currency="RON", term_months=12, amount_minor=100_000))
    processed = await process_matured_deposits()
    assert processed == 0
