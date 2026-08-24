"""Familia "amount" (AMT-01..05) — vezi guardian-claude-code-prompt.md.

Toate funcțiile de aici sunt PURE: citesc doar din `RuleContext`/
`RulesetConfig`, nu ating DB/HTTP/ceasul — vezi fraud/models.py pentru de
ce (determinism cerut de scoring.py).
"""

from datetime import timedelta

from app.fraud.models import RuleContext, RuleOutcome
from app.fraud.ruleset_config import RulesetConfig
from app.fraud.stats import percentile


def _is_cold_start(ctx: RuleContext, ruleset: RulesetConfig) -> bool:
    return ctx.profile.transaction_count < ruleset.cold_start_min_transactions


def _windowed_amounts(ctx: RuleContext, ruleset: RulesetConfig, category: str | None = None) -> list[int]:
    cutoff = ctx.evaluated_at - timedelta(days=ruleset.percentile_window_days)
    return [
        s.amount_minor
        for s in ctx.profile.history_samples
        if s.created_at >= cutoff and (category is None or s.category == category)
    ]


def check_amt_01(ctx: RuleContext, ruleset: RulesetConfig) -> RuleOutcome | None:
    """amount > 2 x p95(user, 90d) — fallback pe cohortă la cold start."""
    cold_start = _is_cold_start(ctx, ruleset)
    if cold_start:
        p95 = ctx.cohort.p95_amount_minor
        multiplier = ruleset.amt01_cold_start_multiplier
        weight = ruleset.amt01_cold_start_weight
    else:
        amounts = _windowed_amounts(ctx, ruleset)
        if len(amounts) < 2:
            return None
        p95 = percentile(amounts, 95)
        multiplier = ruleset.amt01_multiplier
        weight = ruleset.amt01_weight

    if p95 <= 0:
        return None
    threshold = p95 * multiplier
    if ctx.transaction.amount_minor <= threshold:
        return None
    return RuleOutcome(
        rule_id="AMT-01",
        family="amount",
        weight=weight,
        contributes_to_score=True,
        values={
            "amount_minor": ctx.transaction.amount_minor,
            "p95_minor": round(p95),
            "multiplier_used": multiplier,
            "cold_start": cold_start,
        },
    )


def check_amt_02(ctx: RuleContext, ruleset: RulesetConfig) -> RuleOutcome | None:
    """amount > 4 x median(user, category, 90d) — fallback pe cohortă la cold start."""
    cold_start = _is_cold_start(ctx, ruleset)
    category = ctx.transaction.category
    if cold_start:
        median = ctx.cohort.median_amount_minor_by_category.get(category, ctx.cohort.median_amount_minor)
        multiplier = ruleset.amt02_cold_start_multiplier
        weight = ruleset.amt02_cold_start_weight
    else:
        amounts = _windowed_amounts(ctx, ruleset, category=category)
        if len(amounts) < 2:
            return None
        median = percentile(amounts, 50)
        multiplier = ruleset.amt02_multiplier
        weight = ruleset.amt02_weight

    if median <= 0:
        return None
    threshold = median * multiplier
    if ctx.transaction.amount_minor <= threshold:
        return None
    return RuleOutcome(
        rule_id="AMT-02",
        family="amount",
        weight=weight,
        contributes_to_score=True,
        values={
            "amount_minor": ctx.transaction.amount_minor,
            "category": category,
            "category_median_minor": round(median),
            "multiplier_used": multiplier,
            "cold_start": cold_start,
        },
    )


def check_amt_03(ctx: RuleContext, ruleset: RulesetConfig) -> RuleOutcome | None:
    """amount > 0.7 x sold disponibil (astăzi == balance_minor, fără hold)."""
    if ctx.source_balance_minor <= 0:
        return None
    threshold = ruleset.amt03_ratio * ctx.source_balance_minor
    if ctx.transaction.amount_minor <= threshold:
        return None
    return RuleOutcome(
        rule_id="AMT-03",
        family="amount",
        weight=ruleset.amt03_weight,
        contributes_to_score=True,
        values={
            "amount_minor": ctx.transaction.amount_minor,
            "balance_minor": ctx.source_balance_minor,
            "ratio": ruleset.amt03_ratio,
        },
    )


def check_amt_04(ctx: RuleContext, ruleset: RulesetConfig) -> RuleOutcome | None:
    """amount >= 0.98 x sold disponibil (golire de cont)."""
    if ctx.source_balance_minor <= 0:
        return None
    threshold = ruleset.amt04_ratio * ctx.source_balance_minor
    if ctx.transaction.amount_minor < threshold:
        return None
    return RuleOutcome(
        rule_id="AMT-04",
        family="amount",
        weight=ruleset.amt04_weight,
        contributes_to_score=True,
        values={
            "amount_minor": ctx.transaction.amount_minor,
            "balance_minor": ctx.source_balance_minor,
            "ratio": ruleset.amt04_ratio,
        },
    )


def check_amt_05(ctx: RuleContext, ruleset: RulesetConfig) -> RuleOutcome | None:
    """Primul transfer > 5x media, la un user cu < 20 tranzacții istorice.

    La transaction_count == 0 media personală nu există — substituim media
    cohortei (singurul caz de cold start real al acestei reguli; între 1 și
    19 tranzacții media personală, deși mică, e deja bine definită).
    """
    if ctx.profile.transaction_count >= ruleset.amt05_max_prior_transactions:
        return None

    if ctx.profile.transaction_count == 0:
        average = ctx.cohort.average_amount_minor
        weight = ruleset.amt05_cold_start_weight
        cold_start = True
    else:
        amounts = [s.amount_minor for s in ctx.profile.history_samples]
        if not amounts:
            return None
        average = sum(amounts) / len(amounts)
        weight = ruleset.amt05_weight
        cold_start = False

    if average <= 0:
        return None
    threshold = average * ruleset.amt05_multiplier
    if ctx.transaction.amount_minor <= threshold:
        return None
    return RuleOutcome(
        rule_id="AMT-05",
        family="amount",
        weight=weight,
        contributes_to_score=True,
        values={
            "amount_minor": ctx.transaction.amount_minor,
            "average_minor": round(average),
            "multiplier_used": ruleset.amt05_multiplier,
            "cold_start": cold_start,
            "prior_transaction_count": ctx.profile.transaction_count,
        },
    )
