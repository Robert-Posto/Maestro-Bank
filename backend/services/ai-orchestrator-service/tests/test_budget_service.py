"""Teste pentru app/services/budget_service.py — combinarea bugetelor cu
cheltuielile lunii curente (spent/remaining/percent/over_budget)."""

from app.services import budget_service


def _budget(id_: str, name: str, category: str, limit_minor: int, active: bool = True) -> dict:
    return {"id": id_, "name": name, "category": category, "limit_minor": limit_minor, "active": active}


def _spending(by_category: list[dict]) -> dict:
    return {"by_category": by_category}


def test_computes_spent_remaining_and_percent():
    budgets = [_budget("b1", "Restaurante", "restaurants", 90000)]
    spending = _spending([{"category": "restaurants", "amount_minor": 30000, "percentage": 100.0}])

    statuses = budget_service.compute_budget_status(budgets, spending)

    assert statuses == [
        {
            "id": "b1",
            "name": "Restaurante",
            "category": "restaurants",
            "limit_minor": 90000,
            "spent_minor": 30000,
            "remaining_minor": 60000,
            "percent_used": 33.3,
            "over_budget": False,
        }
    ]


def test_category_without_spending_this_month_is_zero_spent():
    budgets = [_budget("b1", "Shopping", "shopping", 100000)]
    statuses = budget_service.compute_budget_status(budgets, _spending([]))

    assert statuses[0]["spent_minor"] == 0
    assert statuses[0]["remaining_minor"] == 100000
    assert statuses[0]["over_budget"] is False


def test_over_budget_flag_when_spent_exceeds_limit():
    budgets = [_budget("b1", "Shopping", "shopping", 50000)]
    spending = _spending([{"category": "shopping", "amount_minor": 70000, "percentage": 100.0}])

    statuses = budget_service.compute_budget_status(budgets, spending)

    assert statuses[0]["over_budget"] is True
    assert statuses[0]["remaining_minor"] == -20000


def test_inactive_budgets_are_excluded():
    budgets = [_budget("b1", "Vechi", "other", 10000, active=False)]
    statuses = budget_service.compute_budget_status(budgets, _spending([]))
    assert statuses == []


def test_multiple_budgets_independent():
    budgets = [
        _budget("b1", "Groceries", "groceries", 100000),
        _budget("b2", "Shopping", "shopping", 50000),
    ]
    spending = _spending(
        [
            {"category": "groceries", "amount_minor": 40000, "percentage": 57.1},
            {"category": "shopping", "amount_minor": 60000, "percentage": 42.9},
        ]
    )

    statuses = budget_service.compute_budget_status(budgets, spending)

    by_category = {s["category"]: s for s in statuses}
    assert by_category["groceries"]["over_budget"] is False
    assert by_category["shopping"]["over_budget"] is True
