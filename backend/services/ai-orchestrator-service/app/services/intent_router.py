"""Clasificator de intenție pentru "un singur loc unde întrebi orice" —
vezi app/routers/assistant.py. Determinist, pe cuvinte-cheie, NU un apel
LLM suplimentar (cost/latență inutile pentru o decizie binară simplă, la
fel ca la content_screening din transactions-service sau detecția de
abonamente din budgets-service — aceeași filosofie: euristică simplă, nu
ML, unde o regulă ajunge).

NU inventează o graniță nouă de domeniu — e EXACT aceeași graniță deja
documentată în app/prompts/support_prompt.py (Support Agent redirecționează
explicit userul spre MaestroAgent pentru buget/prognoză/abonamente, spunând
clar "nu tu gestionezi asta"). Aici doar automatizăm decizia, ca userul să
nu mai aleagă manual pagina.

Support Agent rămâne implicit (catch-all) — orice mesaj care NU se
potrivește clar cu domeniul Spending + Forecast merge la Support, exact
cum Support e deja domeniul "tot restul" (conturi, carduri, tranzacții,
transferuri, depozite, investiții, puncte, credite, documente, tichete).
"""

import re
from typing import Literal

AgentName = Literal["spending_forecast", "support"]

# Fiecare tipar corespunde unui subiect pe care Support Agent ÎL
# REDIRECȚIONEAZĂ deja explicit spre MaestroAgent (vezi support_prompt.py) —
# lista de mai jos NU e o graniță nouă, doar automatizarea celei existente.
# RO + EN, fiindcă userul poate scrie în oricare limbă (comutatorul de limbă
# schimbă UI-ul, nu ce tastează userul).
_SPENDING_FORECAST_PATTERNS = [
    # RO
    r"\bbuget\w*",
    r"\bcheltui\w*",
    r"\beconomis\w*",
    r"\b[îi]mi permit\w*",
    r"\bpermite\w* s[ăa]\b",
    r"\bprognoz\w*",
    r"\bforecast\w*",
    r"\babonament\w*",
    # EN
    r"\bbudget\w*",
    r"\bspend\w*",
    r"\bspent\b",
    r"\bsav(?:e|ing)\w*",
    r"\bcan i afford\b",
    r"\bafford\w*",
    r"\bsubscription\w*",
    r"\bcash[- ]?flow\b",
]

_SPENDING_FORECAST_REGEX = re.compile("|".join(_SPENDING_FORECAST_PATTERNS), re.IGNORECASE)


def classify_intent(message: str) -> AgentName:
    """"spending_forecast" dacă mesajul se potrivește clar cu domeniul
    MaestroAgent, altfel "support" (implicit — Support e deja catch-all)."""
    if _SPENDING_FORECAST_REGEX.search(message):
        return "spending_forecast"
    return "support"
