"""Familia "structuring" — DOAR STR-02 în Faza 1 (STR-01 are nevoie de o
decizie de business despre "pragul de raportare", care nu s-a luat încă —
vezi planul)."""

from app.fraud.models import RuleContext, RuleOutcome
from app.fraud.ruleset_config import RulesetConfig


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
