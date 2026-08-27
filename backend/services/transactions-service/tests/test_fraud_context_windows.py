"""Teste cu Mongo real pentru interogările NOI din app/fraud/context.py —
VEL-03 (_count_new_beneficiaries_last_60min) și STR-01
(_count_near_threshold_last_24h). Testele pure din test_fraud_rules.py
acoperă doar pragul trivial din check_vel_03/check_str_01 — logica REALĂ
de graniță/lookback trăiește aici, în interogările Mongo, deci are nevoie
de o bază reală, nu de fixture-uri sintetice.

fresh_database / clean_fraud_collections (conftest.py) se aplică automat.
tx_db.transactions e propriu acestui fișier (autouse local, mai jos).
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.database import get_database
from app.fraud import context
from app.fraud.ruleset_config import RulesetConfig

pytestmark = pytest.mark.asyncio

RULESET = RulesetConfig()
ACCOUNT_ID = "acc-source"
EVALUATED_AT = datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
async def clean_transactions():
    await get_database().transactions.delete_many({})
    yield
    await get_database().transactions.delete_many({})


async def _seed_tx(**overrides) -> None:
    base = {
        "from_account_id": ACCOUNT_ID,
        "to_account_id": "acc-dest",
        "from_iban": "RO11MAES0000000000000001",
        "to_iban": "RO22MAES0000000000000002",
        "amount_minor": 10_000,
        "currency": "RON",
        "description": "",
        "category": "other",
        "type": "transfer",
        "status": "completed",
        "recognized": False,
        "reported": False,
        "created_at": EVALUATED_AT,
    }
    base.update(overrides)
    await get_database().transactions.insert_one(base)


# --- _first_seen_per_iban (pură, fără DB) -----------------------------------


async def test_first_seen_per_iban_keeps_earliest_occurrence():
    rows = [
        {"to_iban": "A", "created_at": datetime(2026, 1, 1, 0)},
        {"to_iban": "B", "created_at": datetime(2026, 1, 1, 1)},
        {"to_iban": "A", "created_at": datetime(2026, 1, 1, 2)},  # a doua plată către A -- ignorată
    ]
    result = context._first_seen_per_iban(rows)
    assert result == {"A": datetime(2026, 1, 1, 0), "B": datetime(2026, 1, 1, 1)}


async def test_first_seen_per_iban_handles_empty_list():
    assert context._first_seen_per_iban([]) == {}


# --- VEL-03 (_count_new_beneficiaries_last_60min) ---------------------------


async def test_vel03_recipient_paid_before_window_is_not_new():
    await _seed_tx(to_iban="RO22MAES0000000000000002", created_at=EVALUATED_AT - timedelta(days=5))
    await _seed_tx(to_iban="RO22MAES0000000000000002", created_at=EVALUATED_AT - timedelta(minutes=5))

    count = await context._count_new_beneficiaries_last_60min(
        get_database(), account_id=ACCOUNT_ID, evaluated_at=EVALUATED_AT, ruleset=RULESET
    )
    assert count == 0


async def test_vel03_first_ever_payment_in_window_counts_once_even_if_repeated():
    await _seed_tx(to_iban="RO22MAES0000000000000002", created_at=EVALUATED_AT - timedelta(minutes=40))
    await _seed_tx(to_iban="RO22MAES0000000000000002", created_at=EVALUATED_AT - timedelta(minutes=10))

    count = await context._count_new_beneficiaries_last_60min(
        get_database(), account_id=ACCOUNT_ID, evaluated_at=EVALUATED_AT, ruleset=RULESET
    )
    assert count == 1


async def test_vel03_mix_of_new_and_known_recipients():
    # Beneficiar CUNOSCUT (plătit acum 10 zile) -- nu contează ca nou.
    await _seed_tx(to_iban="RO_KNOWN", created_at=EVALUATED_AT - timedelta(days=10))
    await _seed_tx(to_iban="RO_KNOWN", created_at=EVALUATED_AT - timedelta(minutes=30))
    # Doi beneficiari NOI, plătiți prima dată chiar în fereastră.
    await _seed_tx(to_iban="RO_NEW_1", created_at=EVALUATED_AT - timedelta(minutes=20))
    await _seed_tx(to_iban="RO_NEW_2", created_at=EVALUATED_AT - timedelta(minutes=5))

    count = await context._count_new_beneficiaries_last_60min(
        get_database(), account_id=ACCOUNT_ID, evaluated_at=EVALUATED_AT, ruleset=RULESET
    )
    assert count == 2


async def test_vel03_transfer_outside_60min_window_is_not_fetched():
    await _seed_tx(to_iban="RO_TOO_OLD", created_at=EVALUATED_AT - timedelta(minutes=61))

    count = await context._count_new_beneficiaries_last_60min(
        get_database(), account_id=ACCOUNT_ID, evaluated_at=EVALUATED_AT, ruleset=RULESET
    )
    assert count == 0


async def test_vel03_failed_transfer_in_window_is_ignored():
    await _seed_tx(to_iban="RO_FAILED", created_at=EVALUATED_AT - timedelta(minutes=5), status="failed")

    count = await context._count_new_beneficiaries_last_60min(
        get_database(), account_id=ACCOUNT_ID, evaluated_at=EVALUATED_AT, ruleset=RULESET
    )
    assert count == 0


# --- STR-01 (_count_near_threshold_last_24h) --------------------------------
# Prag implicit: 5_000_000 bani (50.000 RON). 90% = 4_500_000, 99% = 4_950_000.


async def test_str01_exactly_90_percent_counts():
    await _seed_tx(amount_minor=4_500_000)
    count = await context._count_near_threshold_last_24h(
        get_database(), account_id=ACCOUNT_ID, evaluated_at=EVALUATED_AT, ruleset=RULESET
    )
    assert count == 1


async def test_str01_exactly_99_percent_counts():
    await _seed_tx(amount_minor=4_950_000)
    count = await context._count_near_threshold_last_24h(
        get_database(), account_id=ACCOUNT_ID, evaluated_at=EVALUATED_AT, ruleset=RULESET
    )
    assert count == 1


async def test_str01_just_below_90_percent_does_not_count():
    await _seed_tx(amount_minor=4_499_999)
    count = await context._count_near_threshold_last_24h(
        get_database(), account_id=ACCOUNT_ID, evaluated_at=EVALUATED_AT, ruleset=RULESET
    )
    assert count == 0


async def test_str01_just_above_99_percent_does_not_count():
    await _seed_tx(amount_minor=4_950_001)
    count = await context._count_near_threshold_last_24h(
        get_database(), account_id=ACCOUNT_ID, evaluated_at=EVALUATED_AT, ruleset=RULESET
    )
    assert count == 0


async def test_str01_counts_three_near_threshold_transactions():
    await _seed_tx(amount_minor=4_600_000, created_at=EVALUATED_AT - timedelta(hours=1))
    await _seed_tx(amount_minor=4_700_000, created_at=EVALUATED_AT - timedelta(hours=2))
    await _seed_tx(amount_minor=4_800_000, created_at=EVALUATED_AT - timedelta(hours=3))
    count = await context._count_near_threshold_last_24h(
        get_database(), account_id=ACCOUNT_ID, evaluated_at=EVALUATED_AT, ruleset=RULESET
    )
    assert count == 3


async def test_str01_outside_24h_window_does_not_count():
    await _seed_tx(amount_minor=4_700_000, created_at=EVALUATED_AT - timedelta(hours=24, minutes=1))
    count = await context._count_near_threshold_last_24h(
        get_database(), account_id=ACCOUNT_ID, evaluated_at=EVALUATED_AT, ruleset=RULESET
    )
    assert count == 0


async def test_str01_failed_transaction_does_not_count():
    await _seed_tx(amount_minor=4_700_000, status="failed")
    count = await context._count_near_threshold_last_24h(
        get_database(), account_id=ACCOUNT_ID, evaluated_at=EVALUATED_AT, ruleset=RULESET
    )
    assert count == 0
