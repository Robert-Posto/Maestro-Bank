"""Tool-uri: cheltuieli + forecast — apelează endpoint-urile de analytics
DEJA EXISTENTE în transactions-service (nu reimplementăm formula de
forecast, o reutilizăm — vezi transactions-service/app/service.py::
get_spending_analytics / get_forecast_analytics).
"""

from __future__ import annotations

from app.services.subscription_dates import days_until_next_billing
from app.tools._client import gateway_get


async def get_spending_summary(authorization_header: str) -> dict:
    """Cheltuielile lunii curente — apelează GET /api/transactions/analytics/spending.

    Shape: {month, total_spent_minor, average_daily_spending_minor, by_category: [{category, amount_minor, percentage}]}
    """
    return await gateway_get("transactions/analytics/spending", authorization_header)


async def get_forecast(authorization_header: str) -> dict:
    """Forecast determinist de sfârșit de lună — apelează
    GET /api/transactions/analytics/forecast (formula: sold curent -
    cheltuieli variabile proiectate - obligații viitoare cunoscute).

    Fiecare element din `upcoming_obligations` primește și
    `days_until_due`/`due_today` — calculate AICI, determinist (vezi
    app/services/subscription_dates.py) — GPT NU trebuie să deducă singur
    "azi"/"peste câte zile" din billing_day + data curentă (risc real de
    halucinație, modelul nu știe sigur data curentă).

    Shape: {current_balance_minor, expected_expenses_minor,
            upcoming_obligations: [{name, amount_minor, billing_day, days_until_due, due_today}, ...],
            estimated_end_of_month_balance_minor, days_remaining_in_month}
    """
    forecast = await gateway_get("transactions/analytics/forecast", authorization_header)
    for obligation in forecast.get("upcoming_obligations", []):
        days = days_until_next_billing(obligation["billing_day"])
        obligation["days_until_due"] = days
        obligation["due_today"] = days == 0
    return forecast


async def get_recent_cash_flow(authorization_header: str, days: int = 30) -> dict:
    """NU e un tool expus modelului (nu apare în tools/registry.py) — folosit
    doar intern de app/services/forecast_service.py, ca să estimeze
    veniturile rămase din ritmul recent de încasări (vezi acolo secțiunea
    despre `remaining_income_minor`). Apelează
    GET /api/transactions/analytics/cash-flow, endpoint deja existent.

    Shape: {period_days, points: [{date, incoming_minor, outgoing_minor, net_minor}]}
    """
    return await gateway_get("transactions/analytics/cash-flow", authorization_header, params={"days": days})
