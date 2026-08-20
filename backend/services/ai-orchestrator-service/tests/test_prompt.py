"""Teste pentru app/prompts/spending_forecast_prompt.py — data curentă
trebuie injectată determinist (nu lăsată la latitudinea modelului)."""

from app.prompts.spending_forecast_prompt import build_system_prompt


def test_build_system_prompt_includes_given_date():
    prompt = build_system_prompt("2026-08-20")
    assert "2026-08-20" in prompt


def test_build_system_prompt_still_forbids_guessing_billing_dates():
    prompt = build_system_prompt("2026-08-20")
    assert "days_until_due" in prompt
