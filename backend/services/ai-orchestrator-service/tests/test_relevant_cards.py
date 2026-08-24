"""Teste pentru app/agents/spending_forecast.py::_relevant_cards — vezi
feedback userului: "as vrea sa mi afiseze asta doar cand e cazul nu mereu"
(cardurile din UI nu mai apar la fiecare răspuns, doar cele relevante
pentru tool-urile pe care GPT a ales SĂ LE CHEME pentru întrebarea asta).
Testele end-to-end (prin endpoint-ul HTTP) sunt în test_agent.py — astea
sunt teste unitare, directe pe funcția de mapare.
"""

from app.agents.spending_forecast import _relevant_cards


def test_no_tools_called_means_no_cards():
    assert _relevant_cards([]) == []


def test_unknown_tool_names_are_ignored():
    assert _relevant_cards(["propose_create_budget", "get_budget_status"]) == []


def test_evaluate_affordability_shows_only_analysis():
    assert _relevant_cards(["evaluate_affordability"]) == ["analysis"]


def test_get_spending_summary_shows_only_estimated_expenses():
    assert _relevant_cards(["get_spending_summary"]) == ["estimated_expenses"]


def test_get_upcoming_subscriptions_shows_only_recurring_payments():
    assert _relevant_cards(["get_upcoming_subscriptions"]) == ["recurring_payments"]


def test_get_account_balance_shows_only_financial_summary():
    assert _relevant_cards(["get_account_balance"]) == ["financial_summary"]


def test_get_forecast_shows_financial_summary_and_estimated_expenses():
    assert _relevant_cards(["get_forecast"]) == ["estimated_expenses", "financial_summary"]


def test_duplicate_tool_calls_do_not_duplicate_cards():
    assert _relevant_cards(["evaluate_affordability", "evaluate_affordability"]) == ["analysis"]


def test_all_tools_called_returns_all_cards_in_stable_ui_order():
    called = [
        "get_account_balance",
        "get_spending_summary",
        "get_forecast",
        "get_upcoming_subscriptions",
        "evaluate_affordability",
    ]
    # Ordinea NU depinde de ordinea în care GPT a chemat tool-urile —
    # e mereu ordinea fixă din UI: analysis, recurring_payments,
    # estimated_expenses, financial_summary.
    assert _relevant_cards(called) == [
        "analysis",
        "recurring_payments",
        "estimated_expenses",
        "financial_summary",
    ]
