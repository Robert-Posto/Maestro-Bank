from app.rates import MIN_DEPOSIT_MINOR, get_rate, list_rates


def test_get_rate_ron_12_months():
    assert get_rate("RON", 12) == 5.75


def test_get_rate_eur_3_months():
    assert get_rate("EUR", 3) == 2.00


def test_list_rates_covers_all_currencies_and_terms():
    rates = list_rates()
    assert len(rates) == 4 * 4  # 4 monede x 4 termene
    currencies = {r["currency"] for r in rates}
    terms = {r["term_months"] for r in rates}
    assert currencies == {"RON", "EUR", "USD", "GBP"}
    assert terms == {3, 6, 12, 24}


def test_min_deposit_defined_for_every_currency():
    assert set(MIN_DEPOSIT_MINOR.keys()) == {"RON", "EUR", "USD", "GBP"}
    assert MIN_DEPOSIT_MINOR["RON"] == 50_000
    assert MIN_DEPOSIT_MINOR["EUR"] == 10_000
