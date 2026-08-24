"""Familia "behaviour" (BEH-01, BEH-02, BEH-03) — pure."""

from app.fraud.models import RuleContext, RuleOutcome
from app.fraud.ruleset_config import RulesetConfig


def check_beh_01(ctx: RuleContext, ruleset: RulesetConfig) -> RuleOutcome | None:
    """Categorie niciodată folosită de acest user — se declanșează normal
    chiar la transaction_count == 0 (prima tranzacție e, corect, și prima
    folosire a categoriei ei)."""
    if ctx.profile.category_counts.get(ctx.transaction.category, 0) > 0:
        return None
    return RuleOutcome(
        rule_id="BEH-01",
        family="behaviour",
        weight=ruleset.beh01_weight,
        contributes_to_score=True,
        values={"category": ctx.transaction.category},
    )


def check_beh_02(ctx: RuleContext, ruleset: RulesetConfig) -> RuleOutcome | None:
    """Categorie < 5% din istoricul userului. Nu se suprapune cu BEH-01 —
    dacă userul n-a mai folosit-o NICIODATĂ (count == 0), semnalul e deja
    acoperit acolo, nu îl dublăm aici."""
    total = ctx.profile.transaction_count
    if total == 0:
        return None
    count = ctx.profile.category_counts.get(ctx.transaction.category, 0)
    if count == 0:
        return None
    share = count / total
    if share >= ruleset.beh02_max_share:
        return None
    return RuleOutcome(
        rule_id="BEH-02",
        family="behaviour",
        weight=ruleset.beh02_weight,
        contributes_to_score=True,
        values={"category": ctx.transaction.category, "share": round(share, 4)},
    )


def check_beh_03(ctx: RuleContext, ruleset: RulesetConfig) -> RuleOutcome | None:
    """Credit intrat urmat de debit ~egal în 2h (pass-through / mulare
    rapidă a fondurilor)."""
    incoming = ctx.window.recent_incoming_credit_minor
    if incoming is None or incoming <= 0:
        return None
    amount = ctx.transaction.amount_minor
    diff_ratio = abs(amount - incoming) / incoming
    if diff_ratio > ruleset.beh03_tolerance_ratio:
        return None
    return RuleOutcome(
        rule_id="BEH-03",
        family="behaviour",
        weight=ruleset.beh03_weight,
        contributes_to_score=True,
        values={
            "outgoing_amount_minor": amount,
            "incoming_amount_minor": incoming,
            "diff_ratio": round(diff_ratio, 4),
        },
    )
