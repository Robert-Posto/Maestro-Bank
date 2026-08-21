"""Familia "temporal" (TIME-01, TIME-02) — pure.

Important (din spec): "noaptea" nu e un semnal — cineva în tură de noapte e
normal activ la 3 dimineața. Ambele reguli sunt relative la userul
individual (sau, la cold start, la cohortă), NICIODATĂ la ore absolute.
"""

from app.fraud.models import RuleContext, RuleOutcome
from app.fraud.ruleset_config import RulesetConfig
from app.fraud.stats import percentile


def _is_cold_start(ctx: RuleContext, ruleset: RulesetConfig) -> bool:
    return ctx.profile.transaction_count < ruleset.cold_start_min_transactions


def check_time_01(ctx: RuleContext, ruleset: RulesetConfig) -> RuleOutcome | None:
    """Ora în afara benzii personale p5-p95 de activitate — fallback pe
    banda cohortei la cold start (banda personală, cu puține eșantioane
    clusterizate, ar fi zgomot, nu semnal)."""
    cold_start = _is_cold_start(ctx, ruleset)
    hour = ctx.evaluated_at.hour
    if cold_start:
        lo, hi = ctx.cohort.hour_p5, ctx.cohort.hour_p95
        weight = ruleset.time01_cold_start_weight
    else:
        hours = [s.hour_utc for s in ctx.profile.history_samples]
        if not hours:
            return None
        lo = round(percentile(hours, 5))
        hi = round(percentile(hours, 95))
        weight = ruleset.time01_weight

    if lo <= hour <= hi:
        return None
    return RuleOutcome(
        rule_id="TIME-01",
        family="temporal",
        weight=weight,
        contributes_to_score=True,
        values={"hour_utc": hour, "personal_band": [lo, hi], "cold_start": cold_start},
    )


def check_time_02(ctx: RuleContext, ruleset: RulesetConfig) -> RuleOutcome | None:
    """Prima activitate după > 90 zile de inactivitate. Gardă: NU se
    declanșează la transaction_count == 0 — nu există `last_transaction_at`
    de comparat, iar "userul nu a mai fost activ niciodată" nu e "dormant"."""
    if ctx.profile.transaction_count == 0 or ctx.profile.last_transaction_at is None:
        return None
    dormant_days = (ctx.evaluated_at - ctx.profile.last_transaction_at).total_seconds() / 86400
    if dormant_days <= ruleset.time02_dormant_days:
        return None
    return RuleOutcome(
        rule_id="TIME-02",
        family="temporal",
        weight=ruleset.time02_weight,
        contributes_to_score=True,
        values={"dormant_days": round(dormant_days, 1)},
    )
