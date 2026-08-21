"""Teste cu Mongo real (via fixture-ul `fresh_database` din conftest.py)
pentru profile.py și cohort.py — upsert idempotent, trunchiere buffer
circular, refresh TTL al cohortei condus de `evaluated_at`, NICIODATĂ de
ceasul de perete."""

from datetime import datetime, timedelta

import pytest

from app.database import get_database
from app.fraud.cohort import get_cohort_baseline
from app.fraud.profile import get_profile, update_profile_after_transfer
from app.fraud.ruleset_config import RulesetConfig

pytestmark = pytest.mark.asyncio

RULESET = RulesetConfig()
EVALUATED_AT = datetime(2026, 8, 20, 12, 0, 0)


async def test_profile_missing_returns_empty_not_error():
    profile = await get_profile("no-such-user")
    assert profile.transaction_count == 0
    assert profile.history_samples == ()


async def test_profile_upsert_creates_and_increments():
    await update_profile_after_transfer(
        user_id="user-1", amount_minor=1_000, category="groceries", to_iban="RO11MAES0000000000000001", created_at=EVALUATED_AT
    )
    await update_profile_after_transfer(
        user_id="user-1",
        amount_minor=2_000,
        category="groceries",
        to_iban="DE11MAES0000000000000001",
        created_at=EVALUATED_AT + timedelta(minutes=5),
    )

    profile = await get_profile("user-1")
    assert profile.transaction_count == 2
    assert profile.category_counts == {"groceries": 2}
    assert set(profile.beneficiary_countries) == {"RO", "DE"}
    assert len(profile.history_samples) == 2
    assert profile.first_transaction_at == EVALUATED_AT
    assert profile.last_transaction_at == EVALUATED_AT + timedelta(minutes=5)


async def test_profile_history_samples_capped_at_300():
    for i in range(305):
        await update_profile_after_transfer(
            user_id="user-2",
            amount_minor=100 + i,
            category="groceries",
            to_iban="RO11MAES0000000000000001",
            created_at=EVALUATED_AT + timedelta(minutes=i),
        )

    profile = await get_profile("user-2")
    assert profile.transaction_count == 305  # contorul all-time NU e plafonat
    assert len(profile.history_samples) == 300  # buffer-ul circular E plafonat
    assert profile.history_samples[-1].amount_minor == 100 + 304  # păstrează cele mai RECENTE


async def test_profile_is_isolated_per_user():
    await update_profile_after_transfer(
        user_id="user-a", amount_minor=100, category="groceries", to_iban="RO11MAES0000000000000001", created_at=EVALUATED_AT
    )
    profile_b = await get_profile("user-b")
    assert profile_b.transaction_count == 0


async def test_cohort_baseline_recomputes_when_missing():
    baseline = await get_cohort_baseline(EVALUATED_AT, RULESET)
    assert baseline.sample_size == 0  # nicio tranzacție "completed" în tx_db-ul de test

    doc = await get_database().fraud_cohort_baseline.find_one({"_id": "global"})
    assert doc is not None
    assert doc["computed_at"] == EVALUATED_AT


async def test_cohort_baseline_reused_within_ttl():
    first = await get_cohort_baseline(EVALUATED_AT, RULESET)
    # Aceeași fereastră de timp (tx_db gol) -> dacă s-ar RECALCULA, tot 0 ar
    # ieși — deci verificăm direct că NU s-a scris un doc nou (computed_at
    # neschimbat), nu doar că rezultatul coincide întâmplător.
    doc_before = await get_database().fraud_cohort_baseline.find_one({"_id": "global"})

    second = await get_cohort_baseline(EVALUATED_AT + timedelta(hours=1), RULESET)
    doc_after = await get_database().fraud_cohort_baseline.find_one({"_id": "global"})

    assert doc_before["computed_at"] == doc_after["computed_at"]  # NU s-a recalculat — încă în TTL
    assert first == second


async def test_cohort_baseline_recomputed_after_ttl_expires():
    await get_cohort_baseline(EVALUATED_AT, RULESET)
    doc_before = await get_database().fraud_cohort_baseline.find_one({"_id": "global"})

    past_ttl = EVALUATED_AT + timedelta(hours=RULESET.cohort_baseline_ttl_hours + 1)
    await get_cohort_baseline(past_ttl, RULESET)
    doc_after = await get_database().fraud_cohort_baseline.find_one({"_id": "global"})

    assert doc_after["computed_at"] == past_ttl  # s-a recalculat, cu noul evaluated_at
    assert doc_after["computed_at"] != doc_before["computed_at"]
