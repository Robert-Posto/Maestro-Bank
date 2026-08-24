"""Familia "velocity" (VEL-01, VEL-02, VEL-05 — VEL-03/VEL-04 excluse din
Faza 1, vezi planul) — pure, vezi rules_amount.py pentru convenția generală.
"""

from datetime import timedelta

from app.fraud.models import RuleContext, RuleOutcome
from app.fraud.ruleset_config import RulesetConfig


def check_vel_01(ctx: RuleContext, ruleset: RulesetConfig) -> RuleOutcome | None:
    """> 5 tranzacții în 10 min (fereastra deja include tranzacția curentă
    — vezi context.py, interogarea rulează după insert)."""
    if ctx.window.count_last_10min <= ruleset.vel01_max_count_10min:
        return None
    return RuleOutcome(
        rule_id="VEL-01",
        family="velocity",
        weight=ruleset.vel01_weight,
        contributes_to_score=True,
        values={"count_last_10min": ctx.window.count_last_10min, "threshold": ruleset.vel01_max_count_10min},
    )


def _daily_average_minor(ctx: RuleContext) -> float:
    cutoff = ctx.evaluated_at - timedelta(days=30)
    amounts = [s.amount_minor for s in ctx.profile.history_samples if s.created_at >= cutoff]
    if not amounts:
        return 0.0
    return sum(amounts) / 30


def check_vel_02(ctx: RuleContext, ruleset: RulesetConfig) -> RuleOutcome | None:
    """Suma cumulată în ultima oră > 3x media zilnică (ultimele 30 zile)."""
    daily_average = _daily_average_minor(ctx)
    if daily_average <= 0:
        return None
    threshold = daily_average * ruleset.vel02_multiplier
    if ctx.window.amount_last_1h_minor <= threshold:
        return None
    return RuleOutcome(
        rule_id="VEL-02",
        family="velocity",
        weight=ruleset.vel02_weight,
        contributes_to_score=True,
        values={
            "amount_last_1h_minor": ctx.window.amount_last_1h_minor,
            "daily_average_minor": round(daily_average),
            "multiplier_used": ruleset.vel02_multiplier,
        },
    )


def check_vel_05(ctx: RuleContext, ruleset: RulesetConfig) -> RuleOutcome | None:
    """Sume escaladante către ACELAȘI beneficiar în 30 min (test-then-drain)."""
    amounts = ctx.window.beneficiary.recent_amounts_same_beneficiary
    if len(amounts) < ruleset.vel05_min_sequence:
        return None
    tail = amounts[-ruleset.vel05_min_sequence :]
    if not all(tail[i] < tail[i + 1] for i in range(len(tail) - 1)):
        return None
    return RuleOutcome(
        rule_id="VEL-05",
        family="velocity",
        weight=ruleset.vel05_weight,
        contributes_to_score=True,
        values={"amounts_minor": list(tail)},
    )
