"""Teste de izolare pentru cele 18 reguli din Faza 1 — funcții pure, FĂRĂ
DB. Fiecare regulă: se declanșează / nu se declanșează / (unde spec-ul
folosește o comparație închisă) exact la graniță. Cazurile de gardă la
istoric zero (BEN-03/TIME-02 sar, BEN-01/BEH-01 se declanșează normal) sunt
ușor de inversat din greșeală — de-aia au teste proprii, explicite.
"""

from datetime import datetime, timedelta

from app.fraud.models import (
    BeneficiaryWindow,
    CohortBaseline,
    DeviceFacts,
    HistorySample,
    RuleContext,
    TransactionSnapshot,
    UserProfileSnapshot,
    WindowFacts,
)
from app.fraud.ruleset_config import RulesetConfig
from app.fraud.rules_amount import check_amt_01, check_amt_02, check_amt_03, check_amt_04, check_amt_05
from app.fraud.rules_behaviour import check_beh_01, check_beh_02, check_beh_03
from app.fraud.rules_beneficiary import check_ben_01, check_ben_03, check_ben_05
from app.fraud.rules_device import check_dev_03
from app.fraud.rules_structuring import check_str_01, check_str_02
from app.fraud.rules_temporal import check_time_01, check_time_02
from app.fraud.rules_velocity import check_vel_01, check_vel_02, check_vel_03, check_vel_05

RULESET = RulesetConfig()
EVALUATED_AT = datetime(2026, 8, 20, 12, 0, 0)  # naiv-UTC, ca tot ce circulă în fraud/ (vezi timeutil.py)


def _tx(**overrides) -> TransactionSnapshot:
    base = dict(
        amount_minor=10_000,
        category="groceries",
        to_iban="RO11MAES0000000000000001",
        from_account_id="acc-1",
        to_account_id="acc-2",
    )
    base.update(overrides)
    return TransactionSnapshot(**base)


def _profile(**overrides) -> UserProfileSnapshot:
    base = dict(
        transaction_count=0,
        first_transaction_at=None,
        last_transaction_at=None,
        history_samples=(),
        category_counts={},
        beneficiary_countries=(),
    )
    base.update(overrides)
    return UserProfileSnapshot(**base)


def _samples(amounts, category="groceries", hour=12, days_ago=10) -> tuple[HistorySample, ...]:
    created = EVALUATED_AT - timedelta(days=days_ago)
    return tuple(HistorySample(amount_minor=a, category=category, hour_utc=hour, created_at=created) for a in amounts)


def _ctx(
    *,
    transaction=None,
    source_balance_minor=1_000_000,
    profile=None,
    window=None,
    cohort=None,
    device=None,
    evaluated_at=EVALUATED_AT,
) -> RuleContext:
    return RuleContext(
        transaction=transaction or _tx(),
        source_balance_minor=source_balance_minor,
        profile=profile or _profile(),
        window=window or WindowFacts(),
        cohort=cohort or CohortBaseline(),
        device=device or DeviceFacts(),
        evaluated_at=evaluated_at,
    )


# --- AMT ---------------------------------------------------------------


def test_amt_01_fires_above_2x_personal_p95():
    profile = _profile(transaction_count=20, history_samples=_samples(list(range(100, 2100, 100))))
    ctx = _ctx(transaction=_tx(amount_minor=100_000), profile=profile)
    assert check_amt_01(ctx, RULESET) is not None


def test_amt_01_no_fire_at_typical_amount():
    profile = _profile(transaction_count=20, history_samples=_samples(list(range(100, 2100, 100))))
    ctx = _ctx(transaction=_tx(amount_minor=500), profile=profile)
    assert check_amt_01(ctx, RULESET) is None


def test_amt_01_cold_start_uses_cohort_p95():
    cohort = CohortBaseline(p95_amount_minor=1_000)
    profile = _profile(transaction_count=3, history_samples=_samples([500, 600, 700]))
    ctx = _ctx(transaction=_tx(amount_minor=3_001), profile=profile, cohort=cohort)  # 3x cohort p95
    outcome = check_amt_01(ctx, RULESET)
    assert outcome is not None
    assert outcome.values["cold_start"] is True
    assert outcome.weight == RULESET.amt01_cold_start_weight


def test_amt_02_fires_above_4x_category_median():
    profile = _profile(transaction_count=20, history_samples=_samples([200] * 5, category="groceries"))
    ctx = _ctx(transaction=_tx(amount_minor=900, category="groceries"), profile=profile)
    assert check_amt_02(ctx, RULESET) is not None  # 900 > 4*200=800


def test_amt_02_no_fire_at_exact_4x_boundary():
    profile = _profile(transaction_count=20, history_samples=_samples([200] * 5, category="groceries"))
    ctx = _ctx(transaction=_tx(amount_minor=800, category="groceries"), profile=profile)
    assert check_amt_02(ctx, RULESET) is None  # strict >, nu >=


def test_amt_03_fires_above_70_percent_balance():
    ctx = _ctx(transaction=_tx(amount_minor=71_000), source_balance_minor=100_000)
    assert check_amt_03(ctx, RULESET) is not None


def test_amt_03_no_fire_at_exact_70_percent_boundary():
    ctx = _ctx(transaction=_tx(amount_minor=70_000), source_balance_minor=100_000)
    assert check_amt_03(ctx, RULESET) is None


def test_amt_04_fires_at_exact_98_percent_boundary():
    ctx = _ctx(transaction=_tx(amount_minor=98_000), source_balance_minor=100_000)
    assert check_amt_04(ctx, RULESET) is not None  # >=, nu >


def test_amt_04_no_fire_just_below_98_percent():
    ctx = _ctx(transaction=_tx(amount_minor=97_999), source_balance_minor=100_000)
    assert check_amt_04(ctx, RULESET) is None


def test_amt_05_fires_for_true_cold_start_over_5x_cohort_average():
    cohort = CohortBaseline(average_amount_minor=1_000)
    ctx = _ctx(transaction=_tx(amount_minor=5_001), profile=_profile(transaction_count=0), cohort=cohort)
    outcome = check_amt_05(ctx, RULESET)
    assert outcome is not None
    assert outcome.values["cold_start"] is True


def test_amt_05_no_fire_after_20_prior_transactions():
    profile = _profile(transaction_count=20, history_samples=_samples([100]))
    ctx = _ctx(transaction=_tx(amount_minor=1_000_000), profile=profile)
    assert check_amt_05(ctx, RULESET) is None


# --- VEL ----------------------------------------------------------------


def test_vel_01_fires_above_5_in_10_minutes():
    ctx = _ctx(window=WindowFacts(count_last_10min=6))
    assert check_vel_01(ctx, RULESET) is not None


def test_vel_01_no_fire_at_exactly_5():
    ctx = _ctx(window=WindowFacts(count_last_10min=5))
    assert check_vel_01(ctx, RULESET) is None


def test_vel_02_fires_above_3x_daily_average():
    profile = _profile(history_samples=_samples([1_000] * 10, days_ago=5))  # medie zilnică ~333
    ctx = _ctx(profile=profile, window=WindowFacts(amount_last_1h_minor=1_001))
    assert check_vel_02(ctx, RULESET) is not None


def test_vel_02_no_fire_without_history():
    ctx = _ctx(window=WindowFacts(amount_last_1h_minor=999_999))
    assert check_vel_02(ctx, RULESET) is None


def test_vel_05_fires_on_escalating_sequence():
    window = WindowFacts(beneficiary=BeneficiaryWindow(recent_amounts_same_beneficiary=(1_000, 2_000, 3_000)))
    assert check_vel_05(_ctx(window=window), RULESET) is not None


def test_vel_05_no_fire_on_non_increasing_sequence():
    window = WindowFacts(beneficiary=BeneficiaryWindow(recent_amounts_same_beneficiary=(3_000, 1_000, 2_000)))
    assert check_vel_05(_ctx(window=window), RULESET) is None


def test_vel_03_fires_at_exactly_3_new_beneficiaries():
    ctx = _ctx(window=WindowFacts(new_beneficiaries_last_60min=3))
    assert check_vel_03(ctx, RULESET) is not None


def test_vel_03_no_fire_below_threshold():
    ctx = _ctx(window=WindowFacts(new_beneficiaries_last_60min=2))
    assert check_vel_03(ctx, RULESET) is None


# --- BEN ------------------------------------------------------------------


def test_ben_01_fires_when_not_seen_before():
    window = WindowFacts(beneficiary=BeneficiaryWindow(seen_before=False))
    assert check_ben_01(_ctx(window=window), RULESET) is not None


def test_ben_01_no_fire_when_seen_before():
    window = WindowFacts(beneficiary=BeneficiaryWindow(seen_before=True))
    assert check_ben_01(_ctx(window=window), RULESET) is None


def test_ben_01_fires_at_zero_history():
    """Prima tranzacție a userului e, corect, și prima plată către acest
    beneficiar — spre deosebire de BEN-03/TIME-02, aici NU e o gardă."""
    ctx = _ctx(profile=_profile(transaction_count=0), window=WindowFacts(beneficiary=BeneficiaryWindow(seen_before=False)))
    assert check_ben_01(ctx, RULESET) is not None


def test_ben_03_fires_for_unknown_country():
    profile = _profile(transaction_count=5, beneficiary_countries=("DE", "FR"))
    ctx = _ctx(transaction=_tx(to_iban="RO11MAES0000000000000001"), profile=profile)
    assert check_ben_03(ctx, RULESET) is not None


def test_ben_03_no_fire_for_known_country():
    profile = _profile(transaction_count=5, beneficiary_countries=("RO", "DE"))
    ctx = _ctx(transaction=_tx(to_iban="RO11MAES0000000000000001"), profile=profile)
    assert check_ben_03(ctx, RULESET) is None


def test_ben_03_skipped_at_zero_history():
    """Primul transfer, prin definiție, nu are 'istoric de țări' — a
    declanșa aici ar fi un fals-pozitiv structural."""
    profile = _profile(transaction_count=0, beneficiary_countries=())
    ctx = _ctx(transaction=_tx(to_iban="RO11MAES0000000000000001"), profile=profile)
    assert check_ben_03(ctx, RULESET) is None


def test_ben_05_fires_but_is_excluded_from_score():
    window = WindowFacts(beneficiary=BeneficiaryWindow(distinct_senders_last_24h=5))
    outcome = check_ben_05(_ctx(window=window), RULESET)
    assert outcome is not None
    assert outcome.contributes_to_score is False


def test_ben_05_no_fire_below_threshold():
    window = WindowFacts(beneficiary=BeneficiaryWindow(distinct_senders_last_24h=4))
    assert check_ben_05(_ctx(window=window), RULESET) is None


# --- TIME -----------------------------------------------------------------


def test_time_01_fires_outside_personal_band():
    profile = _profile(transaction_count=20, history_samples=_samples([100] * 10, hour=10))
    ctx = _ctx(profile=profile, evaluated_at=EVALUATED_AT.replace(hour=3))
    assert check_time_01(ctx, RULESET) is not None


def test_time_01_no_fire_inside_personal_band():
    profile = _profile(transaction_count=20, history_samples=_samples([100] * 10, hour=12))
    ctx = _ctx(profile=profile, evaluated_at=EVALUATED_AT.replace(hour=12))
    assert check_time_01(ctx, RULESET) is None


def test_time_02_fires_after_91_days_dormant():
    profile = _profile(transaction_count=5, last_transaction_at=EVALUATED_AT - timedelta(days=91))
    assert check_time_02(_ctx(profile=profile), RULESET) is not None


def test_time_02_no_fire_at_exactly_90_days():
    profile = _profile(transaction_count=5, last_transaction_at=EVALUATED_AT - timedelta(days=90))
    assert check_time_02(_ctx(profile=profile), RULESET) is None  # strict >


def test_time_02_skipped_at_zero_history():
    profile = _profile(transaction_count=0, last_transaction_at=None)
    assert check_time_02(_ctx(profile=profile), RULESET) is None


# --- DEV ------------------------------------------------------------------


def test_dev_03_fires_within_60_minutes():
    device = DeviceFacts(latest_passkey_created_at=EVALUATED_AT - timedelta(minutes=30), data_available=True)
    assert check_dev_03(_ctx(device=device), RULESET) is not None


def test_dev_03_no_fire_outside_window():
    device = DeviceFacts(latest_passkey_created_at=EVALUATED_AT - timedelta(minutes=61), data_available=True)
    assert check_dev_03(_ctx(device=device), RULESET) is None


def test_dev_03_no_fire_when_auth_service_data_unavailable():
    """Fail-open: date indisponibile (timeout/eroare la auth-service) ->
    regula pur și simplu nu se declanșează, niciodată confundată cu 'nicio
    înrolare recentă' (vezi context.py)."""
    device = DeviceFacts(latest_passkey_created_at=EVALUATED_AT - timedelta(minutes=1), data_available=False)
    assert check_dev_03(_ctx(device=device), RULESET) is None


# --- BEH ------------------------------------------------------------------


def test_beh_01_fires_for_new_category():
    profile = _profile(category_counts={"groceries": 5})
    ctx = _ctx(transaction=_tx(category="entertainment"), profile=profile)
    assert check_beh_01(ctx, RULESET) is not None


def test_beh_01_no_fire_for_known_category():
    profile = _profile(category_counts={"groceries": 5})
    ctx = _ctx(transaction=_tx(category="groceries"), profile=profile)
    assert check_beh_01(ctx, RULESET) is None


def test_beh_01_fires_at_zero_history():
    ctx = _ctx(transaction=_tx(category="groceries"), profile=_profile(transaction_count=0, category_counts={}))
    assert check_beh_01(ctx, RULESET) is not None


def test_beh_02_fires_for_rare_category():
    profile = _profile(transaction_count=100, category_counts={"groceries": 90, "entertainment": 2})
    ctx = _ctx(transaction=_tx(category="entertainment"), profile=profile)
    assert check_beh_02(ctx, RULESET) is not None  # 2/100 = 2% < 5%


def test_beh_02_no_fire_for_frequent_category():
    profile = _profile(transaction_count=100, category_counts={"groceries": 90})
    ctx = _ctx(transaction=_tx(category="groceries"), profile=profile)
    assert check_beh_02(ctx, RULESET) is None


def test_beh_02_no_fire_for_never_used_category():
    """Nu se suprapune cu BEH-01: categoria niciodată folosită e semnalul
    ACELEI reguli, nu se dublează aici."""
    profile = _profile(transaction_count=100, category_counts={"groceries": 90})
    ctx = _ctx(transaction=_tx(category="entertainment"), profile=profile)
    assert check_beh_02(ctx, RULESET) is None


def test_beh_03_fires_for_near_equal_passthrough():
    window = WindowFacts(recent_incoming_credit_minor=10_000)
    ctx = _ctx(transaction=_tx(amount_minor=10_050), window=window)  # 0.5% diff < 2% toleranță
    assert check_beh_03(ctx, RULESET) is not None


def test_beh_03_no_fire_when_amounts_differ():
    window = WindowFacts(recent_incoming_credit_minor=10_000)
    ctx = _ctx(transaction=_tx(amount_minor=15_000), window=window)
    assert check_beh_03(ctx, RULESET) is None


def test_beh_03_no_fire_without_recent_incoming_credit():
    assert check_beh_03(_ctx(window=WindowFacts(recent_incoming_credit_minor=None)), RULESET) is None


# --- STR --------------------------------------------------------------------


def test_str_01_fires_at_exactly_3_near_threshold_transactions():
    ctx = _ctx(window=WindowFacts(near_threshold_count_last_24h=3))
    assert check_str_01(ctx, RULESET) is not None


def test_str_01_no_fire_below_threshold():
    ctx = _ctx(window=WindowFacts(near_threshold_count_last_24h=2))
    assert check_str_01(ctx, RULESET) is None


def test_str_02_fires_for_3_distinct_beneficiaries():
    window = WindowFacts(identical_amount_distinct_beneficiaries_60min=3)
    assert check_str_02(_ctx(window=window), RULESET) is not None


def test_str_02_no_fire_below_threshold():
    window = WindowFacts(identical_amount_distinct_beneficiaries_60min=2)
    assert check_str_02(_ctx(window=window), RULESET) is None
