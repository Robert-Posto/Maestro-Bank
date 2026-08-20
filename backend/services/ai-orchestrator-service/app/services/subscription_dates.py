"""Calcul determinist al zilelor rămase până la următoarea taxare a unui
abonament — GPT NU trebuie să deducă singur "azi"/"peste câte zile" din
`billing_day` + data curentă (risc real de halucinație — modelul nu are
de unde să știe sigur ziua curentă). Python calculează exact aici, tool-urile
(vezi app/tools/transactions_tools.py::get_forecast,
app/tools/budgets_tools.py::get_upcoming_subscriptions) atașează rezultatul
pe fiecare obligație/abonament, iar promptul spune modelului să-l
folosească verbatim.
"""

from __future__ import annotations

import calendar
from datetime import datetime, timezone


def days_until_next_billing(billing_day: int, today: datetime | None = None) -> int:
    """0 = se taxează azi. Dacă ziua a trecut deja luna asta, calculează
    până la aceeași zi din luna URMĂTOARE — cu wraparound corect la
    schimbarea anului și la luni cu mai puține zile (ex. billing_day=31
    într-o lună de februarie -> cade pe ultima zi a lunii, 28/29).
    """
    today = today or datetime.now(timezone.utc)

    if billing_day >= today.day:
        return billing_day - today.day

    days_left_this_month = calendar.monthrange(today.year, today.month)[1] - today.day
    next_month = today.month % 12 + 1
    next_year = today.year + (1 if today.month == 12 else 0)
    days_in_next_month = calendar.monthrange(next_year, next_month)[1]
    effective_next_billing_day = min(billing_day, days_in_next_month)
    return days_left_this_month + effective_next_billing_day
