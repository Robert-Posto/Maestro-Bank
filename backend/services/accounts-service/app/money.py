"""Utilitar pentru formatarea sumelor monetare.

Valoarea CANONICĂ este întotdeauna `*_minor` (bani întregi — 100 bani =
1 RON). NU folosim float pentru bani nicăieri. `format_minor_amount` e
doar pentru afișare (convenience), nu pentru calcule.
"""


def format_minor_amount(amount_minor: int) -> str:
    major, minor = divmod(amount_minor, 100)
    return f"{major}.{minor:02d}"
