"""Familia "beneficiary" (BEN-01, BEN-03, BEN-05 — BEN-02/BEN-04 excluse din
Faza 1, vezi planul) — pure.

BEN-05 e specială: `contributes_to_score=False` — spec-ul sursă o marchează
explicit "post-core only, prea scumpă inline", ceea ce înseamnă că NU are
voie să influențeze decizia tranzacției care o suprafață, doar să informeze
evaluări viitoare. Vezi scoring.py pentru cum e exclusă din calculul
scorului ȘI din ordinea diminishing-returns a familiei ei.
"""

from app.fraud.models import RuleContext, RuleOutcome
from app.fraud.ruleset_config import RulesetConfig


def check_ben_01(ctx: RuleContext, ruleset: RulesetConfig) -> RuleOutcome | None:
    """Prima plată către acest beneficiar — se declanșează normal chiar la
    transaction_count == 0 (primul transfer al userului e, corect, și
    prima plată către acest beneficiar)."""
    if ctx.window.beneficiary.seen_before:
        return None
    return RuleOutcome(
        rule_id="BEN-01",
        family="beneficiary",
        weight=ruleset.ben01_weight,
        contributes_to_score=True,
        values={"to_iban": ctx.transaction.to_iban},
    )


def check_ben_03(ctx: RuleContext, ruleset: RulesetConfig) -> RuleOutcome | None:
    """Țara IBAN-ului absentă din istoricul userului (derivat din prefixul
    IBAN, fără câmp nou stocat). Gardă: NU se declanșează la
    transaction_count == 0 — primul transfer, prin definiție, nu are
    "istoric de țări", iar declanșarea acolo ar fi un fals-pozitiv."""
    if ctx.profile.transaction_count == 0:
        return None
    country = ctx.transaction.to_iban[:2]
    if country in ctx.profile.beneficiary_countries:
        return None
    return RuleOutcome(
        rule_id="BEN-03",
        family="beneficiary",
        weight=ruleset.ben03_weight,
        contributes_to_score=True,
        values={"to_iban_country": country, "known_countries": list(ctx.profile.beneficiary_countries)},
    )


def check_ben_05(ctx: RuleContext, ruleset: RulesetConfig) -> RuleOutcome | None:
    """Beneficiar primind de la >= 5 expeditori distincți în 24h (tipar
    "mulă"). Exclusă din scor — vezi docstring-ul modulului."""
    count = ctx.window.beneficiary.distinct_senders_last_24h
    if count < ruleset.ben05_min_distinct_senders:
        return None
    return RuleOutcome(
        rule_id="BEN-05",
        family="beneficiary",
        weight=ruleset.ben05_weight,
        contributes_to_score=False,
        values={"distinct_senders_last_24h": count, "to_iban": ctx.transaction.to_iban},
    )
