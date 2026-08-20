"""Tool-uri: abonamente + bugete — apelează budgets-service prin Gateway.

Citire (expuse ca tool-uri GPT, vezi app/tools/registry.py):
  get_upcoming_subscriptions, get_budgets

Scriere (NU sunt tool-uri GPT — apelate DOAR din
app/services/budget_actions_service.py::execute_confirmed_action, după ce
userul apasă explicit "Confirmă" în UI, fără GPT în buclă):
  create_budget, update_budget, delete_budget
"""

from __future__ import annotations

from app.services.subscription_dates import days_until_next_billing
from app.tools._client import gateway_delete, gateway_get, gateway_patch, gateway_post


async def get_upcoming_subscriptions(authorization_header: str) -> list[dict]:
    """Toate abonamentele active ale userului (billing_day = ziua din lună
    la care se taxează). app/services/forecast_service.py le împarte în
    "deja plătite" (billing_day < ziua curentă) și "rămase" (>=).

    Fiecare abonament primește și `days_until_due`/`due_today` — zilele
    până la URMĂTOAREA taxare (cu wraparound corect dacă ziua a trecut
    deja luna asta), calculate determinist (vezi app/services/subscription_dates.py)
    — GPT NU trebuie să deducă singur "azi"/"peste câte zile".

    Shape (per element, din budgets-service/app/models.py::SubscriptionOut):
      {id, name, amount_minor, currency, billing_day, category, active, created_at,
       days_until_due, due_today}
    """
    subscriptions = await gateway_get("budgets/subscriptions", authorization_header)
    for subscription in subscriptions:
        days = days_until_next_billing(subscription["billing_day"])
        subscription["days_until_due"] = days
        subscription["due_today"] = days == 0
    return subscriptions


async def get_budgets(authorization_header: str) -> list[dict]:
    """Toate bugetele userului (active sau nu) — apelează GET /api/budgets/budgets.

    Shape (per element, din budgets-service/app/models.py::BudgetOut):
      {id, name, category, limit_minor, period, active, created_at}
    """
    return await gateway_get("budgets/budgets", authorization_header)


async def create_budget(payload: dict, authorization_header: str) -> dict:
    """Execuție REALĂ — apelată doar după confirmare explicită din UI."""
    return await gateway_post("budgets/budgets", authorization_header, json=payload)


async def update_budget(budget_id: str, payload: dict, authorization_header: str) -> dict:
    """Execuție REALĂ — apelată doar după confirmare explicită din UI."""
    return await gateway_patch(f"budgets/budgets/{budget_id}", authorization_header, json=payload)


async def delete_budget(budget_id: str, authorization_header: str) -> None:
    """Execuție REALĂ — apelată doar după confirmare explicită din UI."""
    await gateway_delete(f"budgets/budgets/{budget_id}", authorization_header)
