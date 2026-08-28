"""Teste PURE (fără DB/HTTP) pentru calculul venitului mediu și mesajul de
respingere — vezi app/eligibility.py."""

from datetime import datetime, timedelta, timezone

from app.eligibility import (
    EligibilityResult,
    _average_monthly_income_minor,
    render_rejection_reason,
)


def _tx(*, category: str, direction: str, amount_minor: int, days_ago: int) -> dict:
    # Formatul REAL trimis de transactions-service: naiv, FĂRĂ sufix de fus
    # orar (nici "Z", nici offset) — vezi app/eligibility.py::_parse_utc.
    # Un test cu "+00:00"/"Z" ar fi trecut și cu bug-ul de parsare real
    # (deja întâlnit live) — de-aia reproducem exact forma naivă aici.
    created_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return {
        "category": category,
        "direction": direction,
        "amount_minor": amount_minor,
        "created_at": created_at.replace(tzinfo=None).isoformat(),
    }


def test_average_income_sums_only_incoming_income_category_in_window():
    transactions = [
        _tx(category="income", direction="incoming", amount_minor=500_000, days_ago=10),  # numărat
        _tx(category="income", direction="incoming", amount_minor=500_000, days_ago=40),  # numărat
        _tx(category="income", direction="incoming", amount_minor=500_000, days_ago=100),  # prea vechi
        _tx(category="shopping", direction="outgoing", amount_minor=100_000, days_ago=5),  # nu e venit
        _tx(category="other", direction="incoming", amount_minor=200_000, days_ago=5),  # nu e categoria "income"
    ]
    # (500_000 + 500_000) / 3 = 333_333
    assert _average_monthly_income_minor(transactions) == 333_333


def test_average_income_zero_when_no_income_transactions():
    transactions = [_tx(category="shopping", direction="outgoing", amount_minor=100_000, days_ago=5)]
    assert _average_monthly_income_minor(transactions) == 0


def test_rejection_reason_mentions_missing_income_history_when_zero():
    result = EligibilityResult(
        average_monthly_income_minor=0, max_affordable_installment_minor=0, existing_installments_minor=0
    )
    reason = render_rejection_reason(result, requested_installment_minor=50_000)
    assert "venit" in reason.lower()


def test_rejection_reason_includes_real_numbers_when_over_threshold():
    result = EligibilityResult(
        average_monthly_income_minor=500_000, max_affordable_installment_minor=200_000, existing_installments_minor=150_000
    )
    reason = render_rejection_reason(result, requested_installment_minor=100_000)
    assert "5000,00 lei" in reason  # venitul mediu (500_000 bani)
    assert "500,00 lei" in reason  # disponibil (200_000 - 150_000 = 50_000 bani)
