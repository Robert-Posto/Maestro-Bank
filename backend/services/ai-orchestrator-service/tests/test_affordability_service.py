"""Teste pentru app/services/affordability_service.py — vezi task-ul,
secțiunea 23: affordable=true / affordable=false / lasă exact bufferul /
sub zero / sumă zero / sumă negativă.

Bug real reparat (raportat de user): bufferul folosea `average_daily_spending_minor`
DIN LUNA CALENDARISTICĂ CURENTĂ — o lună cu cheltuieli neobișnuit de mari
(ex. o vacanță) dădea un buffer absurd. Acum bufferul vine dintr-o rată
STABILĂ (fereastră rolantă de 60 de zile, calculată de transactions-service
— vezi get_baseline_daily_rate_minor), trimisă explicit ca
`baseline_daily_rate_minor`, SEPARAT de `spending_summary` (care rămâne
necesar DOAR pentru sfatul de economisire — vezi top_discretionary_category).
"""

import pytest

from app.services import affordability_service


def _spending(by_category: list[dict] | None = None) -> dict:
    return {"by_category": by_category} if by_category is not None else {}


def test_recommended_buffer_is_half_of_thirty_days_average():
    # 100 lei/zi x 30 zile x 0.5 = 1500 lei
    assert affordability_service.recommended_buffer_minor(10000) == 150000


def test_affordable_true_when_buffer_preserved():
    result = affordability_service.evaluate_affordability(
        requested_amount_minor=200000,
        estimated_end_of_month_balance_minor=458861,
        spending_summary=_spending(),
        baseline_daily_rate_minor=3733,  # buffer ~= 56000
    )
    assert result["affordable"] is True
    assert result["estimated_balance_after_purchase_minor"] == 458861 - 200000


def test_affordable_false_when_below_buffer():
    result = affordability_service.evaluate_affordability(
        requested_amount_minor=400000,
        estimated_end_of_month_balance_minor=420000,
        spending_summary=_spending(),
        baseline_daily_rate_minor=10000,  # buffer = 150000
    )
    # rămân 20000, sub bufferul de 150000
    assert result["affordable"] is False


def test_purchase_leaves_exactly_buffer_is_affordable():
    # sold 500000, buffer 150000 (rată de bază 10000/zi) -> suma care lasă EXACT bufferul e 350000
    result = affordability_service.evaluate_affordability(
        requested_amount_minor=350000,
        estimated_end_of_month_balance_minor=500000,
        spending_summary=_spending(),
        baseline_daily_rate_minor=10000,
    )
    assert result["estimated_balance_after_purchase_minor"] == result["recommended_buffer_minor"]
    assert result["affordable"] is True  # >= buffer, nu doar >


def test_purchase_leaves_balance_below_zero_is_not_affordable():
    result = affordability_service.evaluate_affordability(
        requested_amount_minor=900000,
        estimated_end_of_month_balance_minor=500000,
        spending_summary=_spending(),
        baseline_daily_rate_minor=10000,
    )
    assert result["estimated_balance_after_purchase_minor"] < 0
    assert result["affordable"] is False


def test_zero_amount_rejected():
    with pytest.raises(ValueError):
        affordability_service.evaluate_affordability(
            requested_amount_minor=0,
            estimated_end_of_month_balance_minor=500000,
            spending_summary=_spending(),
            baseline_daily_rate_minor=10000,
        )


def test_negative_amount_rejected():
    with pytest.raises(ValueError):
        affordability_service.evaluate_affordability(
            requested_amount_minor=-100,
            estimated_end_of_month_balance_minor=500000,
            spending_summary=_spending(),
            baseline_daily_rate_minor=10000,
        )


def test_render_recommendation_mentions_buffer_when_affordable():
    result = affordability_service.evaluate_affordability(
        requested_amount_minor=200000,
        estimated_end_of_month_balance_minor=458861,
        spending_summary=_spending(),
        baseline_daily_rate_minor=3733,
    )
    text = affordability_service.render_recommendation(result)
    assert "rezervă" in text


def test_render_recommendation_explains_shortfall_when_not_affordable():
    result = affordability_service.evaluate_affordability(
        requested_amount_minor=400000,
        estimated_end_of_month_balance_minor=420000,
        spending_summary=_spending(),
        baseline_daily_rate_minor=10000,
    )
    text = affordability_service.render_recommendation(result)
    assert "Nu recomandăm" in text


def test_render_recommendation_adds_concrete_savings_tip_when_not_affordable():
    spending_summary = _spending(
        [
            {"category": "groceries", "amount_minor": 90000, "percentage": 60.0},
            {"category": "shopping", "amount_minor": 50000, "percentage": 33.3},
        ]
    )
    result = affordability_service.evaluate_affordability(
        requested_amount_minor=400000,
        estimated_end_of_month_balance_minor=420000,
        spending_summary=spending_summary,
        baseline_daily_rate_minor=10000,
    )
    text = affordability_service.render_recommendation(result)
    assert "shopping" in text
    assert "500,00 lei" in text


def test_render_recommendation_no_tip_when_no_discretionary_history():
    result = affordability_service.evaluate_affordability(
        requested_amount_minor=400000,
        estimated_end_of_month_balance_minor=420000,
        spending_summary=_spending(),  # fără by_category
        baseline_daily_rate_minor=10000,
    )
    text = affordability_service.render_recommendation(result)
    assert "cea mai mare cheltuială discreționară" not in text
