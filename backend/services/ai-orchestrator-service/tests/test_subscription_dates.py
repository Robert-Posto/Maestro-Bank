"""Teste pentru app/services/subscription_dates.py — calculul determinist
al zilelor până la următoarea taxare a unui abonament (0 = azi), inclusiv
wraparound la sfârșit de lună/an. Vezi feedback userului: GPT nu are voie
să deducă singur "peste câte zile" — trebuie să fie calculat aici, exact.
"""

from datetime import datetime, timezone

from app.services.subscription_dates import days_until_next_billing


def _date(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 12, 0, tzinfo=timezone.utc)


def test_billing_today_is_zero():
    assert days_until_next_billing(20, today=_date(2026, 8, 20)) == 0


def test_billing_later_this_month():
    assert days_until_next_billing(25, today=_date(2026, 8, 20)) == 5


def test_billing_already_passed_this_month_wraps_to_next_month():
    # azi 20 august, scadența pe 3 -> a trecut deja luna asta, urmează 3 sept.
    # zile rămase în august (11) + 3 (ziua din septembrie) = 14
    assert days_until_next_billing(3, today=_date(2026, 8, 20)) == 14


def test_billing_tomorrow():
    assert days_until_next_billing(21, today=_date(2026, 8, 20)) == 1


def test_wraparound_across_year_boundary():
    # 20 decembrie, scadență pe 5 -> urmează 5 ianuarie anul următor.
    # zile rămase în decembrie (11) + 5 = 16
    assert days_until_next_billing(5, today=_date(2026, 12, 20)) == 16


def test_billing_day_31_still_simple_case_within_31_day_month():
    # billing_day 31 >= today.day 15 -> caz simplu, nu wraparound.
    assert days_until_next_billing(31, today=_date(2026, 1, 15)) == 16


def test_wraparound_clamps_billing_day_to_shorter_next_month():
    # Azi 31 ianuarie, scadență ziua 30 -> a trecut deja luna asta
    # (30 < 31) -> urmează luna următoare, februarie 2026 (an nebisect,
    # 28 zile) -> clamp la 28 (nu există ziua 30 în februarie).
    # zile rămase în ianuarie (31-31=0) + 28 (clamped) = 28
    assert days_until_next_billing(30, today=_date(2026, 1, 31)) == 28
