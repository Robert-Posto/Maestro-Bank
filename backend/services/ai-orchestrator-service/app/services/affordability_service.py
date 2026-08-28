"""Logică determinist Python pentru "Îmi permit X?" — vezi task-ul,
secțiunea 10. GPT NU calculează nimic aici, doar extrage
`requested_amount_minor` din întrebarea în limbaj natural (asta e
interpretare, nu aritmetică) și apelează tool-ul `evaluate_affordability`
(vezi app/tools/registry.py), care rulează codul de mai jos.

Formula (exact ca în task):

    estimated_balance_without_purchase
        = estimated_end_of_month_balance   (deja calculat determinist, vezi
                                             forecast_service / transactions-service)
    estimated_balance_after_purchase
        = estimated_balance_without_purchase - requested_amount
    affordable
        = estimated_balance_after_purchase >= recommended_buffer
"""

# NOTĂ import circular: forecast_service importă recommended_buffer_minor
# de-aici, deci NU putem importa forecast_service la nivel de modul (ar
# crea un cerc). Import local, doar în funcția care chiar are nevoie de
# top_discretionary_category (vezi evaluate_affordability mai jos).
from __future__ import annotations

from app.i18n import current_language, pick

# Buffer-ul recomandat = o regulă simplă, documentată (task-ul, secțiunea
# 10: "NU inventa un algoritm financiar sofisticat") — jumătate dintr-o
# lună de cheltuieli, la ritmul mediu zilnic curent al userului.
BUFFER_SAFETY_FRACTION = 0.5
DAYS_PER_MONTH_FOR_BUFFER = 30


def recommended_buffer_minor(spending_summary: dict) -> int:
    """Buffer de siguranță recomandat, derivat din ritmul mediu de
    cheltuire al userului (average_daily_spending_minor, din
    GET /transactions/analytics/spending) — nu un număr fix hardcodat.
    """
    average_daily_minor = spending_summary.get("average_daily_spending_minor", 0)
    return round(average_daily_minor * DAYS_PER_MONTH_FOR_BUFFER * BUFFER_SAFETY_FRACTION)


def evaluate_affordability(
    *,
    requested_amount_minor: int,
    estimated_end_of_month_balance_minor: int,
    spending_summary: dict,
) -> dict:
    """Verdictul determinist pentru "îmi permit X?". Aruncă ValueError
    pentru sume invalide (<=0) — tratat de tool-ul care apelează asta
    (vezi app/tools/registry.py), NU lăsat să iasă ca 500 brut.
    """
    if requested_amount_minor <= 0:
        raise ValueError("Suma cerută trebuie să fie un număr pozitiv.")

    # Import local — vezi nota de mai sus despre importul circular cu
    # forecast_service.
    from app.services.forecast_service import top_discretionary_category

    buffer_minor = recommended_buffer_minor(spending_summary)
    estimated_balance_without_purchase_minor = estimated_end_of_month_balance_minor
    estimated_balance_after_purchase_minor = estimated_balance_without_purchase_minor - requested_amount_minor
    affordable = estimated_balance_after_purchase_minor >= buffer_minor

    return {
        "requested_amount_minor": requested_amount_minor,
        "affordable": affordable,
        "recommended_buffer_minor": buffer_minor,
        "estimated_balance_without_purchase_minor": estimated_balance_without_purchase_minor,
        "estimated_balance_after_purchase_minor": estimated_balance_after_purchase_minor,
        "top_discretionary_category": top_discretionary_category(spending_summary),
    }


def format_ron(amount_minor: int) -> str:
    """Formatare minimală, DOAR pentru textul `recommendation` (nu pentru
    UI — acolo frontend-ul formatează prin MoneyPipe din amount_minor).
    Urmează limba curentă: "1234,50 lei" (ro) / "1234.50 RON" (en).
    """
    sign = "-" if amount_minor < 0 else ""
    major, minor = divmod(abs(amount_minor), 100)
    if current_language() == "en":
        return f"{sign}{major}.{minor:02d} RON"
    return f"{sign}{major},{minor:02d} lei"


def render_recommendation(result: dict) -> str:
    """Text determinist (NU generat de GPT) pentru câmpul `recommendation`
    — reflectă exact numerele calculate mai sus, ca să nu depindă de
    fidelitatea cu care modelul ar reformula cifrele (task-ul, secțiunea
    4: "nu lăsa GPT să facă aritmetica critică" — extindem asta și la
    parafrazarea rezultatului, nu doar la calculul lui).

    Când cheltuiala NU se încadrează, adăugăm și un sfat de economisire
    CONCRET (categoria discreționară cu cea mai mare cheltuială reală de
    până acum) — nu doar verdictul sec (vezi feedback userului: "sa ma
    ajute sa economisesc, sa mi dea sfaturi").
    """
    buffer_text = format_ron(result["recommended_buffer_minor"])
    if result["affordable"]:
        requested_text = format_ron(result["requested_amount_minor"])
        return pick(
            f"Poți aloca {requested_text}, dar păstrează cel puțin {buffer_text} rezervă pentru cheltuieli neprevăzute.",
            f"You can set aside {requested_text}, but keep at least {buffer_text} as a reserve for unexpected costs.",
        )
    shortfall_minor = result["recommended_buffer_minor"] - result["estimated_balance_after_purchase_minor"]
    after_text = format_ron(result["estimated_balance_after_purchase_minor"])
    shortfall_text = format_ron(shortfall_minor)
    base = pick(
        f"Nu recomandăm această cheltuială acum — ai rămâne cu {after_text}, sub bufferul de "
        f"siguranță recomandat de {buffer_text} (îți lipsesc {shortfall_text}).",
        f"We don't recommend this purchase right now — you'd be left with {after_text}, below the "
        f"recommended safety buffer of {buffer_text} (you're short by {shortfall_text}).",
    )
    top_category = result.get("top_discretionary_category")
    if top_category:
        label, amount_minor = top_category
        amount_text = format_ron(amount_minor)
        base += pick(
            f" Cea mai mare cheltuială discreționară de până acum e pe {label} "
            f"({amount_text}) — reducerea ei e cea mai rapidă cale să-ți acoperi diferența.",
            f" Your largest discretionary spend so far is on {label} "
            f"({amount_text}) — cutting it is the fastest way to close the gap.",
        )
    return base
