"""Familia "velocity" (VEL-01, VEL-02, VEL-03, VEL-04, VEL-05) — pure,
vezi rules_amount.py pentru convenția generală.
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


def check_vel_03(ctx: RuleContext, ruleset: RulesetConfig) -> RuleOutcome | None:
    """>= 3 beneficiari NOI (niciodată plătiți înainte de fereastra
    curentă) în 60 min — diversificare bruscă, distinctă de VEL-01 (volum
    brut, orice beneficiar) și VEL-05 (escaladare către UN SINGUR
    beneficiar)."""
    count = ctx.window.new_beneficiaries_last_60min
    if count < ruleset.vel03_min_new_beneficiaries:
        return None
    return RuleOutcome(
        rule_id="VEL-03",
        family="velocity",
        weight=ruleset.vel03_weight,
        contributes_to_score=True,
        values={"new_beneficiaries_last_60min": count, "threshold": ruleset.vel03_min_new_beneficiaries},
    )


def check_vel_04(ctx: RuleContext, ruleset: RulesetConfig) -> RuleOutcome | None:
    """>= N încercări de login EȘUATE, imediat înainte de cea mai recentă
    reușită — tipar de ghicire a parolei/credential stuffing urmat de
    succes. `recent_logins` vine deja sortat descrescător (cele mai
    recente primele) — găsim cea mai recentă reușită oriunde-ar fi în
    listă (nu presupunem că e neapărat chiar primul element — un login
    ulterior, irelevant, ar putea fi urmat de-o încercare eșuată la o altă
    sesiune, fără legătură cu autentificarea CHIAR folosită la transferul
    curent — vezi planul fazei despre aproximarea "sesiunea curentă")."""
    if not ctx.security.data_available:
        return None
    logins = ctx.security.recent_logins
    success_index = next((i for i, event in enumerate(logins) if event.success), None)
    if success_index is None:
        return None

    consecutive_failures = 0
    for event in logins[success_index + 1 :]:
        if event.success:
            break
        consecutive_failures += 1

    if consecutive_failures < ruleset.vel04_min_failed_attempts:
        return None
    return RuleOutcome(
        rule_id="VEL-04",
        family="velocity",
        weight=ruleset.vel04_weight,
        contributes_to_score=True,
        values={"consecutive_failed_attempts": consecutive_failures, "threshold": ruleset.vel04_min_failed_attempts},
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
