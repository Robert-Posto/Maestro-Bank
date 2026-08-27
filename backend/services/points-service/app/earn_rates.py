"""Rata de câștig a punctelor de loialitate, per categorie de cheltuială.

Politică PROPRIE MaestroBank — nu există un standard extern pentru "câte
puncte pe leu cheltuit", fiecare program de loialitate își stabilește
propriile rate (la fel ca politica de rate a depozitelor, vezi
deposits-service/app/rates.py). `income` e FIX 0% — nu se dau niciodată
puncte pe bani care intră în cont, indiferent de categoria aleasă acolo.

Punctele NU se dau la orice transfer — DOAR la plăți către un cont FĂRĂ user
MaestroBank real atașat (semnalul `to_name is None`, calculat deja de
transactions-service și trimis ca `is_merchant_payment` — vezi
app/service.py::credit_for_transaction). Un transfer către alt user
MaestroBank NU dă niciodată puncte, indiferent de sumă/categorie.

Categoriile sunt cele 9 fixe din transactions-service/app/models.py
::TRANSACTION_CATEGORIES — o a doua copie manual sincronizată, la fel ca
frontend/src/app/shared/categories.ts.
"""

EARN_RATE_PERCENT: dict[str, float] = {
    "groceries": 1.0,
    "transport": 1.0,
    "bills": 0.5,
    "subscriptions": 1.5,
    "other": 1.0,
    "entertainment": 2.5,
    "shopping": 3.0,
    "restaurants": 3.0,
    "income": 0.0,
}

# Câte puncte valorează 1 leu de "valoare aplicată" — cifră rotundă, ca
# procentele mici (0,5%-3%) să producă puncte întregi, ușor de citit în UI.
POINTS_PER_RON = 10


def compute_points_earned(category: str, amount_minor: int) -> int:
    """Puncte câștigate pentru o plată de `amount_minor` bani, în categoria
    dată. 0 dacă rata categoriei e 0 (ex. "income") sau necunoscută."""
    rate_percent = EARN_RATE_PERCENT.get(category, 0.0)
    if rate_percent <= 0:
        return 0
    amount_ron = amount_minor / 100
    return round(amount_ron * rate_percent / 100 * POINTS_PER_RON)


def list_earn_rates() -> list[dict]:
    return [{"category": category, "rate_percent": rate} for category, rate in EARN_RATE_PERCENT.items()]
