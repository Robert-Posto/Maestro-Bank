"""Teste pentru deposits-service.

Apelurile către accounts-service (_get_account_by_user_and_type,
_debit_account, _credit_account) sunt MOCK-uite aici, intenționat — la fel
ca restul serviciilor din acest backend (vezi transactions-service/tests/
test_transfers.py pentru precedent).

Rulare (cu stack-ul pornit prin `docker compose up`, bază de TEST separată):

    docker compose exec deposits-service pip install pytest==8.3.3 pytest-asyncio==0.24.0 httpx==0.27.2 -q
    docker compose exec -e MONGO_URL=mongodb://mongodb:27017/deposits_db_test deposits-service python -m pytest -q
"""

from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from app.database import get_database
from app.main import app
from app.models import DepositOpenRequest

USER_ID = str(ObjectId())
CURRENT_ACCOUNT_ID = str(ObjectId())


@pytest.fixture(autouse=True)
async def clean_deposits():
    await get_database().deposits.delete_many({})
    yield
    await get_database().deposits.delete_many({})


@pytest.fixture
def mock_accounts(monkeypatch):
    state = {"balance_minor": 200_000}  # 2.000,00 RON disponibili

    async def fake_get_account(user_id: str, account_type: str) -> dict:
        assert account_type == "current"
        return {"id": CURRENT_ACCOUNT_ID, "iban": "RO11MAES0000000000000001", "currency": "RON", "balance_minor": state["balance_minor"], "status": "active", "account_type": "current"}

    async def fake_debit(account_id: str, amount_minor: int) -> None:
        assert account_id == CURRENT_ACCOUNT_ID
        if amount_minor > state["balance_minor"]:
            from fastapi import HTTPException, status
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Sold insuficient.")
        state["balance_minor"] -= amount_minor

    async def fake_credit(account_id: str, amount_minor: int) -> None:
        state["balance_minor"] += amount_minor

    monkeypatch.setattr("app.service._get_account_by_user_and_type", fake_get_account)
    monkeypatch.setattr("app.service._debit_account", fake_debit)
    monkeypatch.setattr("app.service._credit_account", fake_credit)
    return state


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_open_deposit_debits_source_account(mock_accounts):
    from app.service import open_deposit

    result = await open_deposit(USER_ID, DepositOpenRequest(currency="RON", term_months=12, amount_minor=100_000))
    assert result.principal_minor == 100_000
    assert result.currency == "RON"
    assert result.term_months == 12
    assert result.rate_percent_annual == 5.75
    assert result.status == "active"
    assert mock_accounts["balance_minor"] == 100_000  # 200.000 - 100.000


async def test_open_deposit_computes_interest_correctly(mock_accounts):
    from app.service import open_deposit

    # 100.000 bani x 5,75% x (12/12) = 5.750 bani dobândă
    result = await open_deposit(USER_ID, DepositOpenRequest(currency="RON", term_months=12, amount_minor=100_000))
    assert result.interest_minor == 5_750


async def test_open_deposit_sets_correct_maturity_date(mock_accounts):
    from app.service import open_deposit

    before = datetime.now(timezone.utc)
    result = await open_deposit(USER_ID, DepositOpenRequest(currency="RON", term_months=3, amount_minor=100_000))
    expected_min = before + timedelta(days=89)
    expected_max = before + timedelta(days=91)
    assert expected_min <= result.matures_at.replace(tzinfo=timezone.utc) <= expected_max


async def test_open_deposit_rejects_amount_below_minimum(mock_accounts):
    from app.service import open_deposit

    with pytest.raises(Exception) as exc_info:
        await open_deposit(USER_ID, DepositOpenRequest(currency="RON", term_months=12, amount_minor=10_000))
    assert exc_info.value.status_code == 400


async def test_open_deposit_propagates_insufficient_funds(mock_accounts):
    from app.service import open_deposit

    with pytest.raises(Exception) as exc_info:
        await open_deposit(USER_ID, DepositOpenRequest(currency="RON", term_months=12, amount_minor=500_000))
    assert exc_info.value.status_code == 409


async def test_list_my_deposits_returns_only_own(mock_accounts):
    from app.service import list_my_deposits, open_deposit

    await open_deposit(USER_ID, DepositOpenRequest(currency="RON", term_months=12, amount_minor=100_000))
    other_user = str(ObjectId())
    await open_deposit(other_user, DepositOpenRequest(currency="RON", term_months=12, amount_minor=60_000))

    mine = await list_my_deposits(USER_ID)
    assert len(mine) == 1
    assert mine[0].principal_minor == 100_000


async def test_open_deposit_http_endpoint_requires_auth(client: AsyncClient):
    response = await client.post("/deposits", json={"currency": "RON", "term_months": 12, "amount_minor": 100_000})
    assert response.status_code == 401


async def test_liquidate_early_returns_only_principal_no_interest(mock_accounts):
    from app.service import liquidate_early, open_deposit

    deposit = await open_deposit(USER_ID, DepositOpenRequest(currency="RON", term_months=12, amount_minor=100_000))
    balance_after_open = mock_accounts["balance_minor"]  # 100.000

    result = await liquidate_early(deposit.id, USER_ID)
    assert result.status == "liquidated_early"
    # Doar principalul revine — NU principal + interest_minor (5.750)
    assert mock_accounts["balance_minor"] == balance_after_open + 100_000


async def test_liquidate_early_rejects_other_users_deposit(mock_accounts):
    from app.service import liquidate_early, open_deposit

    deposit = await open_deposit(USER_ID, DepositOpenRequest(currency="RON", term_months=12, amount_minor=100_000))

    with pytest.raises(Exception) as exc_info:
        await liquidate_early(deposit.id, str(ObjectId()))
    assert exc_info.value.status_code == 404


async def test_liquidate_early_rejects_already_liquidated(mock_accounts):
    from app.service import liquidate_early, open_deposit

    deposit = await open_deposit(USER_ID, DepositOpenRequest(currency="RON", term_months=12, amount_minor=100_000))
    await liquidate_early(deposit.id, USER_ID)

    with pytest.raises(Exception) as exc_info:
        await liquidate_early(deposit.id, USER_ID)
    assert exc_info.value.status_code == 409
