"""Familia "structuring" (STR-01, STR-02) — pure."""

from app.fraud.models import RuleContext, RuleOutcome
from app.fraud.ruleset_config import RulesetConfig


def check_str_01(ctx: RuleContext, ruleset: RulesetConfig) -> RuleOutcome | None:
    """>= 3 tranzacții proprii în 24h, fiecare între 90% și 99% dintr-un
    prag de "raportare" configurabil (implicit 50.000 RON — decizie de
    PRODUS pentru acest demo, NU un prag legal real, vezi
    ruleset_config.py) — tipar tipic de evitare deliberată a unui prag."""
    count = ctx.window.near_threshold_count_last_24h
    if count < ruleset.str01_min_count_24h:
        return None
    return RuleOutcome(
        rule_id="STR-01",
        family="structuring",
        weight=ruleset.str01_weight,
        contributes_to_score=True,
        values={
            "amount_minor": ctx.transaction.amount_minor,
            "near_threshold_count_24h": count,
            "reporting_threshold_minor": ruleset.str01_reporting_threshold_minor,
        },
    )


def check_str_02(ctx: RuleContext, ruleset: RulesetConfig) -> RuleOutcome | None:
    """Aceeași sumă exactă către >= 3 beneficiari diferiți în 60 min."""
    count = ctx.window.identical_amount_distinct_beneficiaries_60min
    if count < ruleset.str02_min_distinct_beneficiaries:
        return None
    return RuleOutcome(
        rule_id="STR-02",
        family="structuring",
        weight=ruleset.str02_weight,
        contributes_to_score=True,
        values={"amount_minor": ctx.transaction.amount_minor, "distinct_beneficiaries_60min": count},
    )
