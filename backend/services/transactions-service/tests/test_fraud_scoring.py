"""Teste pentru scoring.py — cap la 100, diminishing returns per familie,
determinism, excluderea BEN-05 din scor, suprimarea regulilor subsumate
(catalogue.py::SUBSUMED_BY). FĂRĂ DB.

Folosește `apply_diminishing_returns` direct, cu liste de RuleOutcome
construite manual — NU trece prin regulile reale (vezi scoring.py pentru
de ce e separată de `evaluate`), ca să testeze matematica scorului izolat
de pragurile reale ale regulilor.
"""

from datetime import datetime

from app.fraud.models import (
    CohortBaseline,
    DeviceFacts,
    RuleContext,
    RuleOutcome,
    SecurityFacts,
    TransactionSnapshot,
    UserProfileSnapshot,
    WindowFacts,
)
from app.fraud.ruleset_config import RulesetConfig
from app.fraud.scoring import apply_diminishing_returns, evaluate

RULESET = RulesetConfig()
EVALUATED_AT = datetime(2026, 8, 20, 12, 0, 0)


def _ctx() -> RuleContext:
    # Context "neutru" — nicio regulă reală ar trebui să se declanșeze cu
    # aceste valori implicite; suficient pentru testele de determinism/
    # puritate de mai jos, care nu depind de CE anume se declanșează.
    return RuleContext(
        transaction=TransactionSnapshot(
            amount_minor=10_000,
            category="groceries",
            to_iban="RO11MAES0000000000000001",
            from_account_id="acc-1",
            to_account_id="acc-2",
        ),
        source_balance_minor=1_000_000,
        profile=UserProfileSnapshot(transaction_count=25, beneficiary_countries=("RO",)),
        window=WindowFacts(),
        cohort=CohortBaseline(),
        device=DeviceFacts(),
        security=SecurityFacts(),
        evaluated_at=EVALUATED_AT,
    )


def _outcome(rule_id: str, family: str, weight: int, contributes: bool = True) -> RuleOutcome:
    return RuleOutcome(rule_id=rule_id, family=family, weight=weight, contributes_to_score=contributes, values={})


def test_diminishing_returns_applies_100_60_30_by_descending_weight():
    fired = [
        _outcome("A-LOW", "fam", 10),
        _outcome("A-HIGH", "fam", 40),
        _outcome("A-MID", "fam", 20),
    ]
    result = apply_diminishing_returns(fired, RULESET)
    by_id = {r.rule_id: r for r in result.fired_rules}

    assert by_id["A-HIGH"].contribution == 40 * 1.0
    assert by_id["A-MID"].contribution == 20 * 0.6
    assert by_id["A-LOW"].contribution == 10 * 0.3
    assert result.score == round(40 + 12 + 3)


def test_diminishing_returns_fourth_rule_in_family_still_gets_30_percent():
    fired = [_outcome(f"F-{w}", "fam", w) for w in (40, 30, 20, 10)]
    result = apply_diminishing_returns(fired, RULESET)
    by_id = {r.rule_id: r for r in result.fired_rules}

    assert by_id["F-10"].contribution == 10 * 0.3
    assert by_id["F-20"].contribution == 20 * 0.3  # a 3-a regulă -> deja 30%
    assert by_id["F-30"].contribution == 30 * 0.6
    assert by_id["F-40"].contribution == 40 * 1.0


def test_diminishing_returns_tie_break_is_by_rule_id_ascending():
    fired = [_outcome("Z-RULE", "fam", 20), _outcome("A-RULE", "fam", 20)]
    result = apply_diminishing_returns(fired, RULESET)
    by_id = {r.rule_id: r for r in result.fired_rules}

    assert by_id["A-RULE"].contribution == 20 * 1.0  # rule_id mai mic -> primul, credit plin
    assert by_id["Z-RULE"].contribution == 20 * 0.6


def test_families_are_independent():
    fired = [_outcome("A1", "amount", 40), _outcome("V1", "velocity", 40)]
    result = apply_diminishing_returns(fired, RULESET)
    by_id = {r.rule_id: r for r in result.fired_rules}

    # ambele iau credit PLIN — fiecare e prima din propria familie
    assert by_id["A1"].contribution == 40
    assert by_id["V1"].contribution == 40
    assert result.score == 80


def test_score_is_capped_at_100():
    fired = [_outcome(f"R{i}", "amount", 50) for i in range(5)]  # 50 + 30 + 15 + 15 + 15 = 125 brut
    result = apply_diminishing_returns(fired, RULESET)
    assert result.score == 100


def test_ben_05_excluded_from_score_and_from_family_ordering():
    """BEN-05 nu are voie să fure un slot de credit-plin unei reguli reale
    din familia ei, deși ea însăși nu contribuie niciodată."""
    fired = [
        _outcome("BEN-05", "beneficiary", 50, contributes=False),
        _outcome("BEN-01", "beneficiary", 15, contributes=True),
    ]
    result = apply_diminishing_returns(fired, RULESET)
    by_id = {r.rule_id: r for r in result.fired_rules}

    assert by_id["BEN-05"].excluded_from_score is True
    assert by_id["BEN-05"].contribution == 0.0
    assert by_id["BEN-01"].contribution == 15 * 1.0  # credit PLIN, nu 60% — BEN-05 nu a ocupat slotul 1
    assert result.score == 15


# --- Suprimare reguli subsumate (catalogue.py::SUBSUMED_BY) ---------------


def test_amt_03_suppressed_when_amt_04_also_fires():
    """AMT-04 (>=98% sold) implică matematic AMT-03 (>70% sold) — scorarea
    ambelor ar umfla artificial fără niciun semnal nou."""
    fired = [_outcome("AMT-03", "amount", 20), _outcome("AMT-04", "amount", 40)]
    result = apply_diminishing_returns(fired, RULESET)
    by_id = {r.rule_id: r for r in result.fired_rules}

    assert by_id["AMT-04"].contribution == 40  # regula "mamă" ia credit plin
    assert by_id["AMT-03"].excluded_from_score is True
    assert by_id["AMT-03"].contribution == 0.0
    assert result.score == 40


def test_amt_03_scores_normally_without_amt_04():
    fired = [_outcome("AMT-03", "amount", 20)]
    result = apply_diminishing_returns(fired, RULESET)
    assert result.fired_rules[0].contribution == 20
    assert result.fired_rules[0].excluded_from_score is False


def test_ben_01_suppressed_when_ben_03_also_fires():
    """O țară CHIAR nouă (BEN-03) nu poate proveni decât de la un
    beneficiar niciodată plătit înainte (BEN-01) — vezi rules_beneficiary.py."""
    fired = [_outcome("BEN-01", "beneficiary", 15), _outcome("BEN-03", "beneficiary", 20)]
    result = apply_diminishing_returns(fired, RULESET)
    by_id = {r.rule_id: r for r in result.fired_rules}

    assert by_id["BEN-03"].contribution == 20
    assert by_id["BEN-01"].excluded_from_score is True
    assert result.score == 20


def test_ben_01_suppressed_when_dev_06_also_fires_cross_family():
    """DEV-06 (familie "device") subsumă BEN-01 (familie "beneficiary") —
    suprimarea trebuie să funcționeze și CROSS-familie, nu doar în interiorul
    aceleiași familii (diminishing-returns per familie NU ar fi prins asta)."""
    fired = [_outcome("BEN-01", "beneficiary", 15), _outcome("DEV-06", "device", 70)]
    result = apply_diminishing_returns(fired, RULESET)
    by_id = {r.rule_id: r for r in result.fired_rules}

    assert by_id["DEV-06"].contribution == 70
    assert by_id["BEN-01"].excluded_from_score is True
    assert result.score == 70


def test_dev_06_suppresses_dev_01_and_amt_01_simultaneously():
    """Cazul complet — DEV-06 e literal DEV-01 + beneficiar nou + AMT-01
    restatate (vezi rules_device.py::check_dev_06); înainte de fix, cele
    3 reguli-ingredient (una cross-familie, fără diminishing-returns automat)
    puteau împinge scorul la 125 dintr-un SINGUR tipar detectat."""
    fired = [
        _outcome("DEV-06", "device", 70),
        _outcome("DEV-01", "device", 25),
        _outcome("BEN-01", "beneficiary", 15),
        _outcome("AMT-01", "amount", 25),
    ]
    result = apply_diminishing_returns(fired, RULESET)
    by_id = {r.rule_id: r for r in result.fired_rules}

    assert by_id["DEV-06"].contribution == 70
    assert by_id["DEV-01"].excluded_from_score is True
    assert by_id["BEN-01"].excluded_from_score is True
    assert by_id["AMT-01"].excluded_from_score is True
    assert result.score == 70


def test_subsumed_rule_still_appears_in_audit_with_zero_contribution():
    """Suprimarea NU șterge regula din fired_rules — dreptul la explicație
    GDPR (vezi fraud/audit.py) tot trebuie să poată arăta CE s-a declanșat,
    doar că nu contribuie de două ori la scor."""
    fired = [_outcome("AMT-03", "amount", 20), _outcome("AMT-04", "amount", 40)]
    result = apply_diminishing_returns(fired, RULESET)
    rule_ids = {r.rule_id for r in result.fired_rules}
    assert rule_ids == {"AMT-03", "AMT-04"}


def test_no_fired_rules_gives_zero_score_and_pass_band():
    result = apply_diminishing_returns([], RULESET)
    assert result.score == 0
    assert result.decision_would_apply == "pass"


def test_decision_bands_mirror_source_spec():
    assert apply_diminishing_returns([_outcome("R", "fam", 29)], RULESET).decision_would_apply == "pass"
    assert apply_diminishing_returns([_outcome("R", "fam", 30)], RULESET).decision_would_apply == "notify"
    assert apply_diminishing_returns([_outcome("R", "fam", 60)], RULESET).decision_would_apply == "step_up"
    assert apply_diminishing_returns([_outcome("R", "fam", 80)], RULESET).decision_would_apply == "hold"


def test_evaluate_is_deterministic_for_identical_context():
    ctx = _ctx()
    result_a = evaluate(ctx, RULESET)
    result_b = evaluate(ctx, RULESET)
    assert result_a == result_b


def test_evaluate_is_pure_not_identity_based():
    """Două RuleContext construite INDEPENDENT, dar egale ca valoare, dau
    exact același rezultat — proba că evaluate() nu se bazează pe
    identitate de obiect/mutație ascunsă, doar pe valorile din context."""
    assert evaluate(_ctx(), RULESET) == evaluate(_ctx(), RULESET)
