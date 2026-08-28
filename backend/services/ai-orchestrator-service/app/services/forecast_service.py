"""Logică determinist Python care asamblează secțiunile "analysis",
"recurring_payments", "estimated_expenses" și "financial_summary" din DTO
(vezi task-ul, secțiunea 11), pornind de la datele DEJA calculate
determinist de transactions-service (nu reinventăm formula de forecast —
vezi transactions-service/app/service.py::get_forecast_analytics, care
face exact ce cere task-ul, secțiunea 9:

    estimated_end_of_month_balance
        = current_balance - estimated_remaining_variable_spending - upcoming_fixed_payments

Acest modul doar reformatează/desparte acele numere pe cardurile din UI
(vezi UI reference/AI copilot.png) — nu recalculează soldul sau
cheltuielile estimate de la zero.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.i18n import current_language
from app.services.affordability_service import recommended_buffer_minor

# Împărțirea cheltuielilor variabile proiectate (rămase de cheltuit până la
# finalul lunii) în "esențiale/rutină" vs. "discreționare" — o euristică
# SIMPLĂ și documentată (nu ML, nu un model de categorii "corect" absolut),
# bazată pe ponderea categoriilor deja cheltuite luna asta (by_category).
# "subscriptions" și "income" sunt excluse din ambele găleți: abonamentele
# sunt deja numărate separat în `recurring_payments`, iar "income" nu e
# cheltuială.
_ESSENTIAL_CATEGORIES = {"groceries", "transport", "bills"}
_DISCRETIONARY_CATEGORIES = {"shopping", "restaurants", "entertainment", "other"}

_CATEGORY_LABELS_RO = {
    "groceries": "alimente",
    "shopping": "shopping",
    "transport": "transport",
    "bills": "facturi",
    "restaurants": "restaurante",
    "entertainment": "entertainment",
    "subscriptions": "abonamente",
    "other": "alte cheltuieli",
}

_CATEGORY_LABELS_EN = {
    "groceries": "groceries",
    "shopping": "shopping",
    "transport": "transport",
    "bills": "bills",
    "restaurants": "restaurants",
    "entertainment": "entertainment",
    "subscriptions": "subscriptions",
    "other": "other spending",
}


def top_discretionary_category(spending_summary: dict) -> tuple[str, int] | None:
    """Categoria discreționară cu cea mai mare cheltuială ÎNREGISTRATĂ deja
    luna asta (nu o proiecție) — sursa pentru un sfat de economisire
    CONCRET ("aici cheltuiești cel mai mult din ce poți controla ușor"),
    nu un sfat generic desprins de datele reale. Întoarce None dacă nu
    există nicio cheltuială discreționară înregistrată încă.
    """
    by_category = spending_summary.get("by_category", [])
    discretionary = [c for c in by_category if c["category"] in _DISCRETIONARY_CATEGORIES]
    if not discretionary:
        return None
    top = max(discretionary, key=lambda c: c["amount_minor"])
    labels = _CATEGORY_LABELS_EN if current_language() == "en" else _CATEGORY_LABELS_RO
    label = labels.get(top["category"], top["category"])
    return label, top["amount_minor"]


def split_recurring_payments(subscriptions: list[dict], today_day: int | None = None) -> dict:
    """Abonamente active ale lunii curente, împărțite în deja-plătite vs.
    rămase de plată, după `billing_day` (ziua din lună la care se taxează).

    NOTĂ despre numele câmpului `total_remaining_minor`: denumirea vine
    EXACT din specificația primită pentru acest agent — reprezintă totalul
    TUTUROR abonamentelor active ale lunii (nu doar cele nescadente încă).
    """
    today_day = today_day or datetime.now(timezone.utc).day
    active = [s for s in subscriptions if s.get("active", True)]

    total_minor = sum(s["amount_minor"] for s in active)
    already_paid_minor = sum(s["amount_minor"] for s in active if s["billing_day"] < today_day)
    remaining_minor = total_minor - already_paid_minor

    return {
        "total_remaining_minor": total_minor,
        "already_paid_minor": already_paid_minor,
        "remaining_minor": remaining_minor,
    }


def split_estimated_expenses(spending_summary: dict, forecast: dict) -> dict:
    """Cheltuielile variabile proiectate până la finalul lunii (fără
    obligațiile fixe, care apar separat în `recurring_payments`), împărțite
    esențial / discreționar.

    `total_variable_minor` se deduce din `forecast["expected_expenses_minor"]`
    (deja calculat de transactions-service) minus obligațiile viitoare
    cunoscute — NU recalculăm average*zile separat, ca să nu riscăm o
    valoare ușor diferită de cea din forecast (o singură sursă de adevăr).
    """
    upcoming_obligations_minor = sum(o["amount_minor"] for o in forecast.get("upcoming_obligations", []))
    total_variable_minor = max(forecast["expected_expenses_minor"] - upcoming_obligations_minor, 0)

    by_category = spending_summary.get("by_category", [])
    essential_amount = sum(c["amount_minor"] for c in by_category if c["category"] in _ESSENTIAL_CATEGORIES)
    discretionary_amount = sum(c["amount_minor"] for c in by_category if c["category"] in _DISCRETIONARY_CATEGORIES)
    denominator = essential_amount + discretionary_amount

    # Fără istoric în nicio categorie relevantă luna asta -> împărțim
    # egal, ca default sigur (nu 100% într-o singură găleată fără dovezi).
    discretionary_share = (discretionary_amount / denominator) if denominator > 0 else 0.5

    discretionary_minor = round(total_variable_minor * discretionary_share)
    variable_minor = total_variable_minor - discretionary_minor  # scădere, nu recalcul -> suma e mereu exactă

    return {
        "variable_minor": variable_minor,
        "discretionary_minor": discretionary_minor,
        "total_minor": total_variable_minor,
    }


def estimate_remaining_income_minor(cash_flow: dict | None, days_remaining: int) -> int | None:
    """Estimare a veniturilor rămase din RITMUL RECENT de încasări (medie
    zilnică pe fereastra `cash_flow`, proiectată pe zilele rămase din lună)
    — vezi app/tools/transactions_tools.py::get_recent_cash_flow.

    IMPORTANT: NU e un forecast real de salariu (transactions-service nu
    expune azi un asemenea semnal) — e o euristică pe bază de încasări
    istorice reale (transferuri primite, salarii anterioare etc.), nu un
    număr inventat. Întoarce None dacă nu avem date, ca să nu prezentăm
    o cifră falsă (task-ul, secțiunea 15: "nu inventezi solduri").
    """
    if not cash_flow or not cash_flow.get("points"):
        return None
    points = cash_flow["points"]
    total_incoming_minor = sum(p["incoming_minor"] for p in points)
    average_daily_incoming_minor = total_incoming_minor / len(points)
    return round(average_daily_incoming_minor * days_remaining)


def build_financial_summary(account: dict, forecast: dict, remaining_income_minor: int | None) -> dict:
    return {
        "current_balance_minor": account["balance_minor"],
        "remaining_income_minor": remaining_income_minor,
        "projected_expenses_minor": forecast["expected_expenses_minor"],
        "estimated_end_balance_minor": forecast["estimated_end_of_month_balance_minor"],
    }


def build_snapshot(
    *,
    account: dict,
    spending_summary: dict,
    forecast: dict,
    subscriptions: list[dict],
    cash_flow: dict | None = None,
) -> dict:
    """Asamblează secțiunile determinist-calculate ale DTO-ului final —
    vezi app/agents/spending_forecast.py, care apelează asta indiferent
    de întrebare (UI-ul arată toate cardurile mereu, vezi task-ul,
    secțiunea 12), și separat suprapune verdictul de affordability DOAR
    dacă userul a cerut una (vezi app/services/affordability_service.py).
    """
    recurring_payments = split_recurring_payments(subscriptions)
    estimated_expenses = split_estimated_expenses(spending_summary, forecast)
    remaining_income_minor = estimate_remaining_income_minor(cash_flow, forecast["days_remaining_in_month"])
    financial_summary = build_financial_summary(account, forecast, remaining_income_minor)

    analysis = {
        "current_balance_minor": account["balance_minor"],
        "recommended_buffer_minor": recommended_buffer_minor(spending_summary),
    }

    return {
        "analysis": analysis,
        "recurring_payments": recurring_payments,
        "estimated_expenses": estimated_expenses,
        "financial_summary": financial_summary,
    }
