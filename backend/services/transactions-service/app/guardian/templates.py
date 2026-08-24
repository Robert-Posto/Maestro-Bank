"""Fallback determinist, FĂRĂ LLM — folosit când complete_json întoarce
None (nu e configurat, timeout, eroare, răspuns nevalid). Spec-ul cere
explicit: "a fraud alert must never fail to reach the user because an
external API was down" — acest modul e plasa de siguranță. Reutilizează
RULE_DESCRIPTIONS din rule_descriptions.py, ca prompt-ul și fallback-ul să
descrie regulile identic."""

from __future__ import annotations

from app.guardian.rule_descriptions import RULE_DESCRIPTIONS

SAFE_CUSTOMER_PHRASE = "Această tranzacție nu a ridicat niciun semnal de risc."
HELD_CUSTOMER_PHRASE = "Tranzacția a fost reținută pentru verificare — contactează banca pentru mai multe informații."


def build_template_customer_phrase(fired_rule_ids: list[str]) -> str:
    """Frază scurtă, generică — NICIODATĂ nu numește regulile (fallback-ul
    respectă aceeași regulă de "fără ID-uri de regulă" ca și LLM-ul)."""
    if not fired_rule_ids:
        return "Această tranzacție a fost semnalată pentru o verificare suplimentară."
    if len(fired_rule_ids) == 1:
        return "Acest transfer are o caracteristică neobișnuită față de comportamentul tău obișnuit."
    return "Acest transfer are mai multe caracteristici neobișnuite față de comportamentul tău obișnuit."


def build_template_staff_explanation(score: int | None, band: str | None, fired_rules: list[dict]) -> str:
    """Paragraf dens, PENTRU PERSONAL — numește explicit regulile, spre
    deosebire de fraza pentru client de mai sus."""
    if not fired_rules:
        return f"Scor {score}/100, bandă „{band}”. Nicio regulă declanșată înregistrată pentru această evaluare."
    parts = []
    for rule in fired_rules:
        rule_id = rule.get("rule_id", "?")
        description = RULE_DESCRIPTIONS.get(rule_id, "regulă fără descriere înregistrată")
        parts.append(f"{rule_id} ({description})")
    rules_str = "; ".join(parts)
    return f"Scor {score}/100, bandă „{band}”. Reguli declanșate: {rules_str}."
