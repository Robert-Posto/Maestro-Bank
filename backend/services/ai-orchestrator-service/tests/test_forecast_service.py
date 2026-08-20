"""Teste pentru app/services/forecast_service.py — vezi task-ul, secțiunea
22: forecast cu istoric normal / fără tranzacții / cu upcoming
subscriptions / aproape de finalul lunii / la începutul lunii / valori
invalide.
"""

from app.services import forecast_service


def _subscription(name: str, amount_minor: int, billing_day: int, active: bool = True) -> dict:
    return {"name": name, "amount_minor": amount_minor, "billing_day": billing_day, "active": active}


def _category(category: str, amount_minor: int, percentage: float) -> dict:
    return {"category": category, "amount_minor": amount_minor, "percentage": percentage}


# --- split_recurring_payments -----------------------------------------


def test_split_recurring_payments_splits_paid_vs_remaining():
    subs = [_subscription("Netflix", 4999, billing_day=3), _subscription("Spotify", 2999, billing_day=22)]
    result = forecast_service.split_recurring_payments(subs, today_day=15)

    assert result["total_remaining_minor"] == 4999 + 2999
    assert result["already_paid_minor"] == 4999  # billing_day 3 < 15
    assert result["remaining_minor"] == 2999  # billing_day 22 >= 15


def test_split_recurring_payments_no_subscriptions():
    result = forecast_service.split_recurring_payments([], today_day=15)
    assert result == {"total_remaining_minor": 0, "already_paid_minor": 0, "remaining_minor": 0}


def test_split_recurring_payments_near_end_of_month_mostly_paid():
    subs = [_subscription("Netflix", 4999, billing_day=3), _subscription("Vodafone", 6299, billing_day=12)]
    result = forecast_service.split_recurring_payments(subs, today_day=29)

    assert result["already_paid_minor"] == 4999 + 6299
    assert result["remaining_minor"] == 0


def test_split_recurring_payments_start_of_month_mostly_remaining():
    subs = [_subscription("Netflix", 4999, billing_day=20), _subscription("iCloud", 1499, billing_day=25)]
    result = forecast_service.split_recurring_payments(subs, today_day=2)

    assert result["already_paid_minor"] == 0
    assert result["remaining_minor"] == 4999 + 1499


def test_split_recurring_payments_ignores_inactive():
    subs = [_subscription("Old plan", 9999, billing_day=5, active=False)]
    result = forecast_service.split_recurring_payments(subs, today_day=15)
    assert result["total_remaining_minor"] == 0


# --- split_estimated_expenses -------------------------------------------


def test_split_estimated_expenses_splits_by_category_weight():
    spending_summary = {
        "by_category": [
            _category("groceries", 40000, 66.7),  # esențial
            _category("restaurants", 20000, 33.3),  # discreționar
        ]
    }
    forecast = {"expected_expenses_minor": 60000, "upcoming_obligations": []}

    result = forecast_service.split_estimated_expenses(spending_summary, forecast)

    assert result["total_minor"] == 60000
    assert result["variable_minor"] + result["discretionary_minor"] == result["total_minor"]
    # 2/3 esențial, 1/3 discreționar din cheltuiala variabilă proiectată
    assert result["discretionary_minor"] == 20000


def test_split_estimated_expenses_no_history_splits_evenly():
    forecast = {"expected_expenses_minor": 10000, "upcoming_obligations": []}
    result = forecast_service.split_estimated_expenses({"by_category": []}, forecast)

    assert result["total_minor"] == 10000
    assert result["variable_minor"] == result["discretionary_minor"] == 5000


def test_split_estimated_expenses_subtracts_upcoming_obligations():
    forecast = {
        "expected_expenses_minor": 60000,
        "upcoming_obligations": [{"name": "Netflix", "amount_minor": 4999, "billing_day": 20}],
    }
    result = forecast_service.split_estimated_expenses({"by_category": []}, forecast)
    assert result["total_minor"] == 60000 - 4999


def test_split_estimated_expenses_never_negative():
    forecast = {
        "expected_expenses_minor": 1000,
        "upcoming_obligations": [{"name": "Netflix", "amount_minor": 5000, "billing_day": 20}],
    }
    result = forecast_service.split_estimated_expenses({"by_category": []}, forecast)
    assert result["total_minor"] == 0
    assert result["variable_minor"] == 0
    assert result["discretionary_minor"] == 0


# --- estimate_remaining_income_minor -------------------------------------


def test_estimate_remaining_income_minor_projects_recent_average():
    cash_flow = {
        "points": [
            {"date": "2026-08-01", "incoming_minor": 0, "outgoing_minor": 1000, "net_minor": -1000},
            {"date": "2026-08-02", "incoming_minor": 20000, "outgoing_minor": 500, "net_minor": 19500},
        ]
    }
    # medie zilnică încasări = 10000, x 10 zile rămase = 100000
    assert forecast_service.estimate_remaining_income_minor(cash_flow, days_remaining=10) == 100000


def test_estimate_remaining_income_minor_no_data_returns_none():
    assert forecast_service.estimate_remaining_income_minor(None, days_remaining=10) is None
    assert forecast_service.estimate_remaining_income_minor({"points": []}, days_remaining=10) is None


# --- build_snapshot (integrare) ------------------------------------------


def test_build_snapshot_end_to_end():
    account = {"balance_minor": 500000}
    spending_summary = {
        "average_daily_spending_minor": 5000,
        "by_category": [_category("groceries", 30000, 100.0)],
    }
    forecast = {
        "expected_expenses_minor": 80000,
        "upcoming_obligations": [{"name": "Netflix", "amount_minor": 4999, "billing_day": 25}],
        "estimated_end_of_month_balance_minor": 420000,
        "days_remaining_in_month": 10,
    }
    subscriptions = [_subscription("Netflix", 4999, billing_day=25), _subscription("Spotify", 2999, billing_day=3)]

    snapshot = forecast_service.build_snapshot(
        account=account,
        spending_summary=spending_summary,
        forecast=forecast,
        subscriptions=subscriptions,
        cash_flow=None,
    )

    assert snapshot["analysis"]["current_balance_minor"] == 500000
    assert snapshot["financial_summary"]["estimated_end_balance_minor"] == 420000
    assert snapshot["financial_summary"]["remaining_income_minor"] is None  # fără cash_flow
    assert snapshot["recurring_payments"]["total_remaining_minor"] == 4999 + 2999
    assert snapshot["estimated_expenses"]["total_minor"] == 80000 - 4999
