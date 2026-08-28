"""Politica de rate a MaestroBank pentru credite personale.

La fel ca la depozite (vezi deposits-service/app/rates.py) — NU există un
feed public pentru dobânda unui credit de consum: nici băncile reale nu o
iau dintr-o piață live, e stabilită intern, pe bază de risc. Tabelul de mai
jos e politica PROPRIE MaestroBank, documentată cinstit ca atare.

Rata unui credit deja aprobat rămâne FIXĂ pe toată durata lui — modificarea
tabelului de mai jos afectează doar creditele aprobate DUPĂ modificare,
niciodată retroactiv (rata e SALVATĂ pe document la aprobare — vezi
app/service.py::apply_for_loan).
"""

RATE_PERCENT_ANNUAL: dict[int, float] = {
    12: 9.5,
    24: 10.5,
    36: 11.5,
    60: 12.5,
}

MIN_LOAN_MINOR = 100_000  # 1.000,00 RON
MAX_LOAN_MINOR = 5_000_000  # 50.000,00 RON


def get_rate(term_months: int) -> float:
    return RATE_PERCENT_ANNUAL[term_months]


def list_rates() -> list[dict]:
    """Toate termenele disponibile — folosit de GET /loans/rates, ca
    frontend-ul să afișeze dobânzile înainte ca userul să aleagă."""
    return [{"term_months": term, "rate_percent_annual": rate} for term, rate in RATE_PERCENT_ANNUAL.items()]


def compute_monthly_installment_minor(principal_minor: int, rate_percent_annual: float, term_months: int) -> int:
    """Formula STANDARD de amortizare (annuity) — cea folosită de orice
    bancă/calculator de credit real, NU o simplificare:

        rată = P × r × (1+r)^n / ((1+r)^n − 1)

    unde r = dobânda LUNARĂ (rate_percent_annual / 12 / 100), n = numărul
    de rate (term_months). Cazul r=0 (dobândă 0%) e tratat separat, ca să nu
    împărțim la zero — rata devine pur și simplu P/n.
    """
    monthly_rate = rate_percent_annual / 12 / 100
    if monthly_rate == 0:
        return round(principal_minor / term_months)
    factor = (1 + monthly_rate) ** term_months
    installment = principal_minor * monthly_rate * factor / (factor - 1)
    return round(installment)
