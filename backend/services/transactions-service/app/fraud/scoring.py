"""Scorarea — SINGURA logică care combină rezultatele regulilor într-un
scor 0-100. Pură: aceleași input-uri, mereu același rezultat (RuleContext e
complet imuabil, nu se citește ceasul aici — vezi fraud/models.py).

`apply_diminishing_returns` e separată de `evaluate` special ca să fie
testabilă cu liste de RuleOutcome construite direct de teste (vezi
tests/test_fraud_scoring.py) — fără să fie nevoie să se reverse-engineerească
praguri reale de reguli doar ca să se declanșeze un anumit număr de reguli
dintr-o familie."""

from app.fraud.catalogue import RULES, SUBSUMED_BY
from app.fraud.models import RuleContext, RuleOutcome, ScoredRule, ScoreResult
from app.fraud.ruleset_config import RulesetConfig


def _map_score_to_band(score: int, ruleset: RulesetConfig) -> str:
    if score >= ruleset.band_hold_min:
        return "hold"
    if score >= ruleset.band_step_up_min:
        return "step_up"
    if score >= ruleset.band_notify_min:
        return "notify"
    return "pass"


def _suppress_subsumed_rules(fired: list[RuleOutcome]) -> list[RuleOutcome]:
    """O regulă subsumată (vezi catalogue.py::SUBSUMED_BY) nu aduce niciun
    semnal nou dacă regula ei "mamă" a fost declanșată și ea — suprimată aici
    (contributes_to_score=False), NU eliminată din listă, ca să rămână
    vizibilă în audit exact ca BEN-05."""
    fired_ids = {outcome.rule_id for outcome in fired}
    suppressed: list[RuleOutcome] = []
    for outcome in fired:
        parents = SUBSUMED_BY.get(outcome.rule_id, ())
        if outcome.contributes_to_score and any(parent in fired_ids for parent in parents):
            outcome = outcome.model_copy(update={"contributes_to_score": False})
        suppressed.append(outcome)
    return suppressed


def apply_diminishing_returns(fired: list[RuleOutcome], ruleset: RulesetConfig) -> ScoreResult:
    fired = _suppress_subsumed_rules(fired)
    by_family: dict[str, list[RuleOutcome]] = {}
    for outcome in fired:
        by_family.setdefault(outcome.family, []).append(outcome)

    scored: list[ScoredRule] = []
    total = 0.0
    for family_outcomes in by_family.values():
        # Doar regulile eligibile pentru scor participă la ordinea
        # diminishing-returns a familiei — o regulă exclusă (ex. BEN-05) NU
        # are voie să "fure" un slot de credit-plin unei reguli reale, deși
        # ea însăși nu contribuie niciodată la scor.
        scoring_eligible = [o for o in family_outcomes if o.contributes_to_score]
        excluded = [o for o in family_outcomes if not o.contributes_to_score]

        # Descrescător după greutate — cel mai sever semnal din familie ia
        # mereu creditul plin; egalitate se rupe după rule_id (determinist).
        scoring_eligible.sort(key=lambda o: (-o.weight, o.rule_id))
        for index, outcome in enumerate(scoring_eligible):
            multiplier_index = min(index, len(ruleset.diminishing_multipliers) - 1)
            multiplier = ruleset.diminishing_multipliers[multiplier_index]
            contribution = outcome.weight * multiplier
            total += contribution
            scored.append(
                ScoredRule(
                    rule_id=outcome.rule_id,
                    family=outcome.family,
                    weight=outcome.weight,
                    contribution=contribution,
                    excluded_from_score=False,
                    values=outcome.values,
                )
            )

        for outcome in excluded:
            scored.append(
                ScoredRule(
                    rule_id=outcome.rule_id,
                    family=outcome.family,
                    weight=outcome.weight,
                    contribution=0.0,
                    excluded_from_score=True,
                    values=outcome.values,
                )
            )

    score = min(ruleset.score_cap, round(total))
    decision = _map_score_to_band(score, ruleset)

    # Ordine stabilă (pe rule_id) în audit log — explicit, nu ne bazăm pe
    # ordinea de inserare a dict-ului by_family ca "detaliu de implementare".
    scored.sort(key=lambda s: s.rule_id)

    return ScoreResult(
        score=score,
        fired_rules=tuple(scored),
        decision_would_apply=decision,
        ruleset_version=ruleset.version,
    )


def evaluate(ctx: RuleContext, ruleset: RulesetConfig) -> ScoreResult:
    fired: list[RuleOutcome] = []
    for spec in RULES:
        outcome = spec.check_fn(ctx, ruleset)
        if outcome is not None:
            fired.append(outcome)
    return apply_diminishing_returns(fired, ruleset)
