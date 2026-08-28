"""Teste PURE (fără DB) pentru formula de amortizare — vezi app/rates.py."""

import pytest

from app.rates import compute_monthly_installment_minor


def test_zero_rate_splits_principal_evenly():
    assert compute_monthly_installment_minor(120_000, 0.0, 12) == 10_000


def test_matches_known_amortization_constant():
    """Factorul de recuperare a capitalului (A/P) pentru i=1%/lună, n=12
    luni e o constantă financiară cunoscută: ≈0,0888487887. La 10.000 lei
    principal, rata ≈888,49 lei."""
    installment = compute_monthly_installment_minor(1_000_000, 12.0, 12)
    assert installment == pytest.approx(88_849, abs=2)


def test_higher_rate_means_higher_installment_for_same_principal_and_term():
    low_rate = compute_monthly_installment_minor(1_000_000, 9.5, 24)
    high_rate = compute_monthly_installment_minor(1_000_000, 12.5, 24)
    assert high_rate > low_rate


def test_longer_term_means_lower_installment_for_same_principal_and_rate():
    short_term = compute_monthly_installment_minor(1_000_000, 10.5, 12)
    long_term = compute_monthly_installment_minor(1_000_000, 10.5, 60)
    assert long_term < short_term
