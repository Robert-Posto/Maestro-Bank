"""Utilitar pentru formatarea sumelor monetare (vezi și accounts-service/app/money.py).

Valoarea CANONICĂ este întotdeauna `amount_minor` (bani întregi). NU
folosim float pentru bani nicăieri.
"""


def format_minor_amount(amount_minor: int) -> str:
    major, minor = divmod(amount_minor, 100)
    return f"{major}.{minor:02d}"
