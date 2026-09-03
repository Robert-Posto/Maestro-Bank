"""Teste pentru app/service.py::get_forecast_analytics — proiecția
cheltuielilor rămase din lună — și get_baseline_daily_rate_minor, rata
zilnică STABILĂ (fereastră rolantă de 60 de zile) folosită atât pentru
proiecție cât și pentru buffer-ul de siguranță (vezi
ai-orchestrator-service/app/services/affordability_service.py).

Bug real #1 (raportat de user): formula veche înmulțea media zilnică
(total cheltuit / zile trecute DIN LUNA CALENDARISTICĂ) — care include
categoria "bills" — cu zilele rămase din lună. O singură factură mare,
devreme în lună, umfla media și, extrapolată liniar, producea o proiecție
absurdă. Fix #1: exclude "bills"/"subscriptions" din baza de calcul.

Bug real #2 (reprodus DIN GREȘEALĂ chiar de o sesiune de test — o
tranzacție unică mare, categorie "other", devreme în lună, a reprodus
EXACT același simptom): fix #1 nu acoperea o cheltuială discreționară
mare, unică, în ORICE categorie. Fix #2: orice tranzacție INDIVIDUALĂ ≥
pragul de "transfer mare" al băncii e exclusă, indiferent de categorie.

Bug real #3 (raportat de user — "dacă am o lună de vacanță, mereu îmi
calculează un buffer nebun"): fix #1+#2 tot foloseau ca NUMITOR "zilele
trecute DIN LUNA CALENDARISTICĂ CURENTĂ" — devreme în lună (numitor mic)
sau într-o lună cu cheltuieli neobișnuit de mari, rata tot ieșea instabilă.
Fix #3: renunță complet la granița lunii calendaristice pentru rata de
bază — o fereastră ROLANTĂ, FIXĂ, de 60 de zile (get_baseline_daily_rate_minor),
independentă de "ziua 1 a lunii" — o lună excepțională se diluează automat
în restul ferestrei, în loc s-o domine cât timp e "luna curentă".

`average_daily_spending_minor` (statul general, afișat userului pe pagina
Spending) rămâne neschimbat de toate cele 3 fix-uri — vezi get_spending_analytics.
"""

from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId

from app.database import get_database
from app.service import get_baseline_daily_rate_minor, get_forecast_analytics

pytestmark = pytest.mark.asyncio

USER_ID = str(ObjectId())
ACCOUNT_ID = str(ObjectId())

ACCOUNT = {
    "id": ACCOUNT_ID,
    "user_id": USER_ID,
    "iban": "RO11MAES0000000000000001",
    "currency": "RON",
    "balance_minor": 1_044_643,  # 10.446,43 lei
    "status": "active",
}

_BASELINE_WINDOW_DAYS = 60


@pytest.fixture(autouse=True)
async def clean_transactions():
    await get_database().transactions.delete_many({})
    yield
    await get_database().transactions.delete_many({})


@pytest.fixture
def mock_dependencies(monkeypatch):
    async def fake_get_account_by_user(user_id: str) -> dict:
        return ACCOUNT

    async def fake_get_subscriptions(user_id: str) -> list[dict]:
        return []

    monkeypatch.setattr("app.service._get_account_by_user", fake_get_account_by_user)
    monkeypatch.setattr("app.service._get_subscriptions_for_user", fake_get_subscriptions)


async def _insert_transaction(days_ago: int, amount_minor: int, category: str) -> None:
    now = datetime.now(timezone.utc)
    await get_database().transactions.insert_one(
        {
            "from_account_id": ACCOUNT_ID,
            "to_account_id": str(ObjectId()),
            "amount_minor": amount_minor,
            "category": category,
            "status": "completed",
            "created_at": now - timedelta(days=days_ago),
            "description": "test",
        }
    )


# --- get_baseline_daily_rate_minor -----------------------------------------


async def test_baseline_rate_uses_fixed_60_day_denominator(mock_dependencies):
    """Verificare directă a formulei — SPRE DEOSEBIRE de vechea rată bazată
    pe luna calendaristică, numitorul e mereu 60, indiferent de câte zile
    au trecut din luna curentă."""
    await _insert_transaction(days_ago=1, amount_minor=30_000, category="groceries")

    rate = await get_baseline_daily_rate_minor(USER_ID)

    assert rate == round(30_000 / _BASELINE_WINDOW_DAYS)


async def test_baseline_rate_excludes_bills_and_large_transactions(mock_dependencies):
    await _insert_transaction(days_ago=1, amount_minor=100_000, category="bills")  # exclus
    await _insert_transaction(days_ago=1, amount_minor=420_000, category="other")  # exclus (≥ 500 RON)
    await _insert_transaction(days_ago=1, amount_minor=10_000, category="groceries")  # inclus

    rate = await get_baseline_daily_rate_minor(USER_ID)

    assert rate == round(10_000 / _BASELINE_WINDOW_DAYS)


async def test_baseline_rate_ignores_transactions_outside_60_day_window(mock_dependencies):
    """O cheltuială de acum 90 de zile (în afara ferestrei) nu trebuie să
    influențeze rata de azi."""
    await _insert_transaction(days_ago=90, amount_minor=500_000, category="groceries")  # în afara ferestrei
    await _insert_transaction(days_ago=1, amount_minor=10_000, category="groceries")  # în fereastră

    rate = await get_baseline_daily_rate_minor(USER_ID)

    assert rate == round(10_000 / _BASELINE_WINDOW_DAYS)


async def test_vacation_month_gets_diluted_not_amplified(mock_dependencies):
    """Scenariul EXACT raportat de user: o "lună de vacanță", cu cheltuieli
    mari mai devreme în fereastra de 60 de zile, NU mai domină singură
    rata — se diluează în restul perioadei fără cheltuieli, spre deosebire
    de vechea formulă (bazată pe zile trecute din luna calendaristică
    curentă), unde ziua 1-2 a lunii ar fi dat un numitor minuscul."""
    # "Vacanța" — cheltuieli sub pragul de transfer mare, dar multe, acum 45 zile.
    for _ in range(10):
        await _insert_transaction(days_ago=45, amount_minor=45_000, category="restaurants")  # 450 lei fiecare

    rate = await get_baseline_daily_rate_minor(USER_ID)

    # Vechea formulă (zile trecute din luna curentă, posibil doar 1-3 zile)
    # ar fi dat o rată de ordinul 150.000-450.000 bani/zi. Fereastra fixă de
    # 60 de zile o diluează la o valoare mult mai mică și stabilă.
    total_vacation_spent = 10 * 45_000
    assert rate == round(total_vacation_spent / _BASELINE_WINDOW_DAYS)
    assert rate < 45_000  # sub cheltuiala unei SINGURE zile de vacanță


# --- get_forecast_analytics (folosește get_baseline_daily_rate_minor) ------


async def test_large_one_off_bill_does_not_inflate_projection(mock_dependencies):
    await _insert_transaction(days_ago=0, amount_minor=114_500, category="bills")
    await _insert_transaction(days_ago=0, amount_minor=1_000, category="other")

    result = await get_forecast_analytics(USER_ID)

    assert result["expected_expenses_minor"] < 50_000
    assert result["estimated_end_of_month_balance_minor"] > 0


async def test_large_one_off_discretionary_purchase_does_not_inflate_projection(mock_dependencies):
    await _insert_transaction(days_ago=0, amount_minor=420_000, category="other")  # exclus (≥ 500 RON)
    await _insert_transaction(days_ago=0, amount_minor=1_000, category="groceries")  # inclus

    result = await get_forecast_analytics(USER_ID)

    assert result["expected_expenses_minor"] < 50_000


async def test_forecast_exposes_baseline_daily_rate(mock_dependencies):
    await _insert_transaction(days_ago=1, amount_minor=30_000, category="groceries")

    result = await get_forecast_analytics(USER_ID)

    assert result["baseline_daily_rate_minor"] == round(30_000 / _BASELINE_WINDOW_DAYS)


async def test_no_transactions_yields_zero_projection(mock_dependencies):
    result = await get_forecast_analytics(USER_ID)

    assert result["expected_expenses_minor"] == 0
    assert result["estimated_end_of_month_balance_minor"] == ACCOUNT["balance_minor"]


async def test_upcoming_subscriptions_still_added_separately(mock_dependencies, monkeypatch):
    """subscriptions e exclusă din rata de bază (ca să nu se dubleze), dar
    obligațiile viitoare CUNOSCUTE (billing_day) tot se adaugă normal, din
    upcoming_obligations."""

    async def fake_get_subscriptions(user_id: str) -> list[dict]:
        return [{"name": "Netflix", "amount_minor": 4999, "billing_day": 25, "active": True}]

    monkeypatch.setattr("app.service._get_subscriptions_for_user", fake_get_subscriptions)

    result = await get_forecast_analytics(USER_ID)

    assert result["upcoming_obligations"] == [{"name": "Netflix", "amount_minor": 4999, "billing_day": 25}]
    assert result["expected_expenses_minor"] >= 4999
