"""Logică determinist Python pentru statusul bugetelor — combină bugetele
(limite, din budgets-service) cu cheltuielile lunii curente (din
transactions-service) ca să răspundă la "cât mai pot cheltui pe X",
"am depășit vreun buget", "ce bugete am active".

NU e un calcul nou/inventat — e exact formula deja folosită de pagina
Bugete din Angular (vezi docstring-ul routers/budgets.py din
budgets-service: "spent/remaining/progres% se calculează combinând acest
răspuns cu GET /transactions/analytics/spending"), doar reprodusă aici
pentru agent.
"""

from __future__ import annotations


def compute_budget_status(budgets: list[dict], spending_summary: dict) -> list[dict]:
    spent_by_category = {c["category"]: c["amount_minor"] for c in spending_summary.get("by_category", [])}

    statuses = []
    for budget in budgets:
        if not budget.get("active", True):
            continue
        spent_minor = spent_by_category.get(budget["category"], 0)
        remaining_minor = budget["limit_minor"] - spent_minor
        percent_used = round((spent_minor / budget["limit_minor"]) * 100, 1) if budget["limit_minor"] else 0.0

        statuses.append(
            {
                "id": budget["id"],
                "name": budget["name"],
                "category": budget["category"],
                "limit_minor": budget["limit_minor"],
                "spent_minor": spent_minor,
                "remaining_minor": remaining_minor,
                "percent_used": percent_used,
                "over_budget": spent_minor > budget["limit_minor"],
            }
        )
    return statuses
