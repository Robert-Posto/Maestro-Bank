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

from __future__ import annotations

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
    }


def format_ron(amount_minor: int) -> str:
    """Formatare minimală, DOAR pentru textul `recommendation` (nu pentru
    UI — acolo frontend-ul formatează prin MoneyPipe din amount_minor).
    """
    sign = "-" if amount_minor < 0 else ""
    major, minor = divmod(abs(amount_minor), 100)
    return f"{sign}{major},{minor:02d} lei"


def render_recommendation(result: dict) -> str:
    """Text determinist (NU generat de GPT) pentru câmpul `recommendation`
    — reflectă exact numerele calculate mai sus, ca să nu depindă de
    fidelitatea cu care modelul ar reformula cifrele (task-ul, secțiunea
    4: "nu lăsa GPT să facă aritmetica critică" — extindem asta și la
    parafrazarea rezultatului, nu doar la calculul lui).
    """
    buffer_text = format_ron(result["recommended_buffer_minor"])
    if result["affordable"]:
        return (
            f"Poți aloca {format_ron(result['requested_amount_minor'])}, "
            f"dar păstrează cel puțin {buffer_text} rezervă pentru cheltuieli neprevăzute."
        )
    shortfall_minor = result["recommended_buffer_minor"] - result["estimated_balance_after_purchase_minor"]
    return (
        f"Nu recomandăm această cheltuială acum — ai rămâne cu "
        f"{format_ron(result['estimated_balance_after_purchase_minor'])}, sub bufferul de "
        f"siguranță recomandat de {buffer_text} (îți lipsesc {format_ron(shortfall_minor)})."
    )
