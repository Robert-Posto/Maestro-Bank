"""Teste pentru app/guardian/templates.py — fallback-ul FĂRĂ LLM."""

import re

from app.guardian.rule_hints import RULE_ANALYST_HINTS
from app.guardian.templates import (
    HELD_CUSTOMER_PHRASE,
    SAFE_CUSTOMER_PHRASE,
    build_template_customer_phrase,
    build_template_staff_explanation,
)

_RULE_ID_PATTERN = re.compile(r"\b[A-Z]{3}-\d{2}\b")


def test_customer_phrase_never_contains_a_rule_id():
    for fired_rule_ids in ([], ["AMT-01"], ["AMT-01", "BEN-01", "TIME-02"]):
        phrase = build_template_customer_phrase(fired_rule_ids)
        assert not _RULE_ID_PATTERN.search(phrase)
        assert phrase  # niciodată gol


def test_staff_explanation_never_contains_a_rule_id():
    """Analistul vede deja regulile separat, pe pagină — raportul trebuie să
    fie un paragraf natural, nu o listă de coduri (vezi rule_hints.py)."""
    fired_rules = [
        {"rule_id": "AMT-04", "family": "amount", "values": {}},
        {"rule_id": "BEN-01", "family": "beneficiary", "values": {}},
    ]
    explanation = build_template_staff_explanation(score=95, band="hold", fired_rules=fired_rules)
    assert not _RULE_ID_PATTERN.search(explanation)
    assert "95" not in explanation
    assert "hold" not in explanation


def test_staff_explanation_weaves_hints_for_each_fired_rule_into_one_paragraph():
    fired_rules = [
        {"rule_id": "AMT-04", "family": "amount", "values": {}},
        {"rule_id": "BEN-01", "family": "beneficiary", "values": {}},
    ]
    explanation = build_template_staff_explanation(score=95, band="hold", fired_rules=fired_rules)
    assert RULE_ANALYST_HINTS["AMT-04"] in explanation
    assert RULE_ANALYST_HINTS["BEN-01"] in explanation


def test_staff_explanation_unknown_rule_id_is_skipped_not_crashed():
    explanation = build_template_staff_explanation(score=10, band="notify", fired_rules=[{"rule_id": "ZZZ-99", "family": "x", "values": {}}])
    assert explanation  # nu crapă, cade pe mesajul generic


def test_staff_explanation_handles_no_fired_rules():
    explanation = build_template_staff_explanation(score=0, band="pass", fired_rules=[])
    assert explanation  # nu crapă, nu e gol


def test_safe_and_held_constants_are_romanian_and_nonempty():
    assert SAFE_CUSTOMER_PHRASE
    assert HELD_CUSTOMER_PHRASE
    assert "reținut" in HELD_CUSTOMER_PHRASE.lower() or "reținută" in HELD_CUSTOMER_PHRASE.lower()


def test_customer_phrase_length_bound_is_reasonable():
    phrase = build_template_customer_phrase(["AMT-01", "AMT-02", "AMT-03", "AMT-04", "AMT-05"])
    assert len(phrase) < 300
