"""Fallback determinist, FĂRĂ LLM — folosit când complete_json întoarce
None (nu e configurat, timeout, eroare, răspuns nevalid). Spec-ul cere
explicit: "a fraud alert must never fail to reach the user because an
external API was down" — acest modul e plasa de siguranță. Reutilizează
RULE_DESCRIPTIONS din rule_descriptions.py, ca prompt-ul și fallback-ul să
descrie regulile identic."""

from __future__ import annotations

from app.guardian.rule_hints import RULE_ANALYST_HINTS

SAFE_CUSTOMER_PHRASE = "Această tranzacție nu a ridicat niciun semnal de risc."
HELD_CUSTOMER_PHRASE = "Tranzacția a fost reținută pentru verificare — contactează banca pentru mai multe informații."

_NO_SIGNALS_STAFF_EXPLANATION = (
    "Nu există un motiv punctual identificat pentru scorul acestei evaluări — verifică manual detaliile tranzacției."
)


def build_template_customer_phrase(fired_rule_ids: list[str]) -> str:
    """Frază scurtă, generică — NICIODATĂ nu numește regulile (fallback-ul
    respectă aceeași regulă de "fără ID-uri de regulă" ca și LLM-ul)."""
    if not fired_rule_ids:
        return "Această tranzacție a fost semnalată pentru o verificare suplimentară."
    if len(fired_rule_ids) == 1:
        return "Acest transfer are o caracteristică neobișnuită față de comportamentul tău obișnuit."
    return "Acest transfer are mai multe caracteristici neobișnuite față de comportamentul tău obișnuit."


def build_template_staff_explanation(score: int | None, band: str | None, fired_rules: list[dict]) -> str:
    """Paragraf în limbaj natural, PENTRU ANALISTUL de fraudă — explică pe
    scurt, pe rând, ce înseamnă fiecare semnal declanșat și ce ar putea
    verifica/întreba analistul, ca un coleg cu experiență, NU o listă de
    ID-uri de regulă (analistul le vede deja separat, pe pagină — vezi
    RULE_ANALYST_HINTS din rule_hints.py, gata scrise în stilul cerut)."""
    if not fired_rules:
        return _NO_SIGNALS_STAFF_EXPLANATION
    hints = []
    for rule in fired_rules:
        hint = RULE_ANALYST_HINTS.get(rule.get("rule_id", ""))
        if hint:
            hints.append(hint)
    if not hints:
        return _NO_SIGNALS_STAFF_EXPLANATION
    return " ".join(hints)
