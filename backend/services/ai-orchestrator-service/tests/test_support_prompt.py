"""Teste pentru app/prompts/support_prompt.py — data curentă trebuie
injectată determinist (nu lăsată la latitudinea modelului), la fel ca la
spending_forecast_prompt.py (vezi test_prompt.py). Esențial pentru
get_transactions_by_date_range: un user care scrie "15 august" fără an
are nevoie ca modelul să știe anul curent, nu să-l ghicească.
"""

from app.prompts.support_prompt import build_support_system_prompt


def test_build_support_system_prompt_includes_given_date():
    prompt = build_support_system_prompt("2026-08-28")
    assert "2026-08-28" in prompt


def test_build_support_system_prompt_mentions_transactions_by_date_range_tool():
    prompt = build_support_system_prompt("2026-08-28")
    assert "get_transactions_by_date_range" in prompt


def test_build_support_system_prompt_still_includes_language_directive():
    prompt = build_support_system_prompt("2026-08-28", language="en")
    assert "Reply EXCLUSIVELY in English" in prompt
