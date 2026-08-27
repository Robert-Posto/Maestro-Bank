"""Teste pentru ramura de cold start / fallback pe cohortă — FĂRĂ DB.

Fiecare test construiește DOUĂ contexte altfel identice, diferind DOAR în
`profile.transaction_count` (sub/peste pragul de 20), cu numerele personale
și cele de cohortă deliberat în dezacord — ca să se probeze că ramura de
cold start CHIAR înlocuiește comparația cu una pe cohortă + greutate
redusă, nu doar că "tot se declanșează"."""

from datetime import datetime, timedelta

from app.fraud.models import (
    CohortBaseline,
    DeviceFacts,
    HistorySample,
    RuleContext,
    SecurityFacts,
    TransactionSnapshot,
    UserProfileSnapshot,
    WindowFacts,
)
from app.fraud.ruleset_config import RulesetConfig
from app.fraud.rules_amount import check_amt_01
from app.fraud.rules_temporal import check_time_01

RULESET = RulesetConfig()
EVALUATED_AT = datetime(2026, 8, 20, 12, 0, 0)


def _tx(amount_minor: int) -> TransactionSnapshot:
    return TransactionSnapshot(
        amount_minor=amount_minor, category="groceries", to_iban="RO11MAES0000000000000001",
        from_account_id="acc-1", to_account_id="acc-2",
    )


def _ctx(*, transaction_count: int, history_samples=(), cohort: CohortBaseline, amount_minor: int, evaluated_at=EVALUATED_AT) -> RuleContext:
    return RuleContext(
        transaction=_tx(amount_minor),
        source_balance_minor=10_000_000,
        profile=UserProfileSnapshot(transaction_count=transaction_count, history_samples=history_samples),
        window=WindowFacts(),
        cohort=cohort,
        device=DeviceFacts(),
        security=SecurityFacts(),
        evaluated_at=evaluated_at,
    )


def test_amt_01_cold_start_ignores_personal_history_uses_cohort():
    # Personal p95 (din cele câteva eșantioane) ar spune "nu se declanșează"
    # la 3.000 — cohorta (mult mai mare) ar spune "se declanșează". Userul
    # e sub pragul de cold start (transaction_count=5 < 20) -> trebuie
    # folosită cohorta, nu istoricul personal.
    personal_samples = tuple(
        HistorySample(amount_minor=10_000, category="groceries", hour_utc=12, created_at=EVALUATED_AT - timedelta(days=1))
        for _ in range(5)
    )  # p95 personal ~10.000 -> 2x = 20.000, threshold NEATINS la 3.000
    cohort = CohortBaseline(p95_amount_minor=1_000)  # 3x (cold-start multiplier) = 3.000

    ctx = _ctx(transaction_count=5, history_samples=personal_samples, cohort=cohort, amount_minor=3_001)
    outcome = check_amt_01(ctx, RULESET)

    assert outcome is not None
    assert outcome.values["cold_start"] is True
    assert outcome.values["p95_minor"] == 1_000  # cohorta, NU cele 10.000 din istoricul personal
    assert outcome.weight == RULESET.amt01_cold_start_weight
    assert outcome.weight < RULESET.amt01_weight  # greutate redusă la cold start


def test_amt_01_established_user_ignores_cohort_uses_personal_history():
    """La transaction_count >= 20, aceleași date — dar acum se folosește
    istoricul personal, NU cohorta, cu greutatea/multiplicatorul complete."""
    personal_samples = tuple(
        HistorySample(amount_minor=10_000, category="groceries", hour_utc=12, created_at=EVALUATED_AT - timedelta(days=1))
        for _ in range(20)
    )
    cohort = CohortBaseline(p95_amount_minor=1_000)  # ar declanșa dacă ar fi folosită

    ctx = _ctx(transaction_count=20, history_samples=personal_samples, cohort=cohort, amount_minor=3_001)
    outcome = check_amt_01(ctx, RULESET)

    # 3.001 < 2 x 10.000 (p95 personal) -> NU se declanșează, deși cohorta
    # (dacă ar fi fost folosită greșit) ar fi spus "da"
    assert outcome is None


def test_time_01_cold_start_uses_cohort_hour_band():
    cohort = CohortBaseline(hour_p5=8, hour_p95=20)  # ora 3 e în afara benzii cohortei
    personal_samples = tuple(
        HistorySample(amount_minor=100, category="groceries", hour_utc=3, created_at=EVALUATED_AT - timedelta(days=1))
        for _ in range(3)
    )  # dacă s-ar folosi istoricul personal, ora 3 ar fi CHIAR banda tipică -> nu s-ar declanșa

    ctx = _ctx(
        transaction_count=3, history_samples=personal_samples, cohort=cohort, amount_minor=100,
        evaluated_at=EVALUATED_AT.replace(hour=3),
    )
    outcome = check_time_01(ctx, RULESET)

    assert outcome is not None
    assert outcome.values["cold_start"] is True
    assert outcome.values["personal_band"] == [8, 20]  # banda cohortei, NU [3, 3] din istoricul personal
    assert outcome.weight == RULESET.time01_cold_start_weight
