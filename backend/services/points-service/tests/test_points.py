"""Teste pentru points-service.

Apelurile către accounts-service (_get_current_account, _credit_account)
sunt MOCK-uite aici, la fel ca la deposits-service/investments-service.

Rulare (cu stack-ul pornit prin `docker compose up`, bază de TEST separată):

    docker compose exec points-service pip install pytest==8.3.3 pytest-asyncio==0.24.0 httpx==0.27.2 -q
    docker compose exec -e MONGO_URL=mongodb://mongodb:27017/points_db_test points-service python -m pytest -q
"""

import pytest
from bson import ObjectId
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.database import get_database
from app.main import app

USER_ID = str(ObjectId())
CURRENT_ACCOUNT_ID = str(ObjectId())


@pytest.fixture(autouse=True)
async def clean_collections():
    db = get_database()
    await db.ledger_entries.delete_many({})
    yield
    await db.ledger_entries.delete_many({})


@pytest.fixture
def mock_accounts(monkeypatch):
    credited = {"total_minor": 0}

    async def fake_get_current_account(user_id: str) -> dict:
        return {
            "id": CURRENT_ACCOUNT_ID,
            "iban": "RO_CURRENT",
            "currency": "RON",
            "balance_minor": 100_000,
            "status": "active",
            "account_type": "current",
        }

    async def fake_credit(account_id: str, amount_minor: int) -> None:
        assert account_id == CURRENT_ACCOUNT_ID
        credited["total_minor"] += amount_minor

    monkeypatch.setattr("app.service._get_current_account", fake_get_current_account)
    monkeypatch.setattr("app.service._credit_account", fake_credit)
    return credited


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --- Câștig puncte (credit-for-transaction) -------------------------------------


async def test_credit_for_transaction_earns_points_for_merchant_payment():
    from app.service import credit_for_transaction, get_balance

    result = await credit_for_transaction(USER_ID, "restaurants", 10_000, True)  # 100 lei @ 3% -> 30 puncte
    assert result.points_earned == 30

    balance = await get_balance(USER_ID)
    assert balance.balance == 30


async def test_credit_for_transaction_gives_zero_for_real_user_transfer():
    from app.service import credit_for_transaction, get_balance

    result = await credit_for_transaction(USER_ID, "restaurants", 10_000, False)
    assert result.points_earned == 0
    balance = await get_balance(USER_ID)
    assert balance.balance == 0


async def test_credit_for_transaction_gives_zero_for_income_category():
    from app.service import credit_for_transaction, get_balance

    result = await credit_for_transaction(USER_ID, "income", 500_000, True)
    assert result.points_earned == 0
    balance = await get_balance(USER_ID)
    assert balance.balance == 0


async def test_credit_for_transaction_computes_per_category_rate():
    from app.service import credit_for_transaction

    result = await credit_for_transaction(USER_ID, "shopping", 20_000, True)  # 200 lei @ 3% -> 60 puncte
    assert result.points_earned == 60


# --- Recompense ---------------------------------------------------------------


async def test_redeem_reward_debits_points_and_credits_ron(mock_accounts):
    from app.service import credit_for_transaction, redeem_reward

    await credit_for_transaction(USER_ID, "restaurants", 200_000, True)  # 2000 lei -> 600 puncte
    result = await redeem_reward(USER_ID, "cashback_10")  # costă 500 puncte, dă 10 lei

    assert result.ron_credited_minor == 1_000
    assert result.new_balance == 100
    assert mock_accounts["total_minor"] == 1_000


async def test_redeem_reward_rejects_insufficient_points(mock_accounts):
    from app.service import redeem_reward

    with pytest.raises(HTTPException) as exc_info:
        await redeem_reward(USER_ID, "cashback_10")
    assert exc_info.value.status_code == 409


async def test_redeem_reward_rejects_unknown_reward(mock_accounts):
    from app.service import redeem_reward

    with pytest.raises(HTTPException) as exc_info:
        await redeem_reward(USER_ID, "not-a-real-reward")
    assert exc_info.value.status_code == 404


# --- Roata norocului -------------------------------------------------------------


async def test_spin_wheel_rejects_wager_above_balance(mock_accounts):
    from app.service import spin_wheel

    with pytest.raises(HTTPException) as exc_info:
        await spin_wheel(USER_ID, 100)
    assert exc_info.value.status_code == 409


async def test_spin_wheel_deducts_wager_regardless_of_outcome(mock_accounts):
    from app.service import credit_for_transaction, get_balance, spin_wheel

    await credit_for_transaction(USER_ID, "restaurants", 200_000, True)  # 600 puncte
    balance_before = (await get_balance(USER_ID)).balance

    result = await spin_wheel(USER_ID, 100)

    assert result.new_balance == balance_before - 100


async def test_spin_wheel_credits_ron_only_when_segment_has_a_prize(monkeypatch, mock_accounts):
    import app.service as service_module
    from app.service import credit_for_transaction, spin_wheel

    await credit_for_transaction(USER_ID, "restaurants", 200_000, True)

    monkeypatch.setattr(
        service_module,
        "_pick_weighted_segment",
        lambda wagered: {"id": "medium_50", "label": "50 lei cashback", "reward_value_minor": 5_000},
    )
    result = await spin_wheel(USER_ID, 100)

    assert result.winning_segment_id == "medium_50"
    assert result.ron_credited_minor == 5_000
    assert mock_accounts["total_minor"] == 5_000


async def test_spin_wheel_gives_no_ron_on_a_losing_segment(monkeypatch, mock_accounts):
    import app.service as service_module
    from app.service import credit_for_transaction, spin_wheel

    await credit_for_transaction(USER_ID, "restaurants", 200_000, True)

    monkeypatch.setattr(
        service_module,
        "_pick_weighted_segment",
        lambda wagered: {"id": "nothing_1", "label": "Nimic de data asta", "reward_value_minor": None},
    )
    result = await spin_wheel(USER_ID, 100)

    assert result.ron_credited_minor is None
    assert mock_accounts["total_minor"] == 0


async def test_wheel_weighted_distribution_shifts_toward_wins_with_higher_wager():
    """Statistic, nu exact — dar diferența (~35% vs ~68% șansă la orice
    premiu) e suficient de mare încât să nu fie plauzibil să pice invers."""
    from app.service import _pick_weighted_segment
    from app.wheel_segments import REFERENCE_WAGER

    trials = 500
    low_wager_wins = sum(1 for _ in range(trials) if _pick_weighted_segment(0)["reward_value_minor"] is not None)
    high_wager_wins = sum(
        1 for _ in range(trials) if _pick_weighted_segment(REFERENCE_WAGER)["reward_value_minor"] is not None
    )

    assert high_wager_wins > low_wager_wins


# --- Endpoint HTTP -----------------------------------------------------------------


async def test_balance_endpoint_requires_auth(client: AsyncClient):
    response = await client.get("/points/balance")
    assert response.status_code == 401
