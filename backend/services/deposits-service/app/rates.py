"""Politica de rate a MaestroBank pentru depozite la termen.

Spre deosebire de cursul valutar (exchange-service/app/bnr_rates.py, care
IA cursul real, zilnic, de la BNR), NU există un feed public curat pentru
dobânzi de depozit: BNR publică doar rata de politică monetară (schimbată
rar, fără feed structurat), iar băncile reale oricum își stabilesc propriile
rate de depozit ca politică internă, nu direct din piață. Tabelul de mai jos
e deci politica PROPRIE MaestroBank — documentată cinstit ca atare, nu
pretinsă ca sursă externă (decizie confirmată explicit cu userul — vezi
docs/superpowers/specs/2026-08-27-deposits-design.md, secțiunea "Rata
dobânzii").

Rata unui depozit deja deschis rămâne FIXĂ pe toată durata lui — modificarea
tabelului de mai jos afectează doar depozitele deschise/reînnoite DUPĂ
modificare, niciodată retroactiv (vezi app/service.py::open_deposit,
process_matured_deposits — rata e SALVATĂ pe document la deschidere).
"""

RATES_PERCENT_ANNUAL: dict[str, dict[int, float]] = {
    "RON": {3: 5.00, 6: 5.50, 12: 5.75, 24: 5.25},
    "EUR": {3: 2.00, 6: 2.25, 12: 2.50, 24: 2.25},
    "USD": {3: 3.50, 6: 3.75, 12: 4.00, 24: 3.75},
    "GBP": {3: 3.75, 6: 4.00, 12: 4.25, 24: 4.00},
}

# Sumă minimă per monedă, în bani/cenți — evită depozite-jucărie.
MIN_DEPOSIT_MINOR: dict[str, int] = {
    "RON": 50_000,  # 500,00 RON
    "EUR": 10_000,  # 100,00 EUR
    "USD": 10_000,  # 100,00 USD
    "GBP": 10_000,  # 100,00 GBP
}


def get_rate(currency: str, term_months: int) -> float:
    return RATES_PERCENT_ANNUAL[currency][term_months]


def list_rates() -> list[dict]:
    """Toate combinațiile monedă×termen — folosit de GET /deposits/rates,
    ca frontend-ul să afișeze ratele înainte ca userul să aleagă."""
    return [
        {"currency": currency, "term_months": term_months, "rate_percent_annual": rate}
        for currency, terms in RATES_PERCENT_ANNUAL.items()
        for term_months, rate in terms.items()
    ]
