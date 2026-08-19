"""Configurație + dataset DEMO de curs valutar pentru exchange-service.

⚠️ NU e o integrare FX reală — nu există nicio conexiune la o piață
valutară/bancă centrală. Ratele de mai jos sunt un dataset STATIC de
development, suficient pentru a demonstra fluxul de UI (curs, spread,
comision, cost total), NEVER de folosit ca sursă de adevăr financiară.
Fiecare răspuns al acestui serviciu marchează explicit `is_demo: true`.
"""

import os


class Settings:
    mongo_url: str = os.getenv("MONGO_URL", "mongodb://localhost:27017/exchange_db")
    jwt_secret: str = os.getenv("JWT_SECRET", "change-me-in-development")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")


settings = Settings()

# Curs DEMO exprimat ca "RON per 1 unitate de valută străină" (curs mid,
# fără spread). Actualizat manual — NU e alimentat dintr-o piață reală.
DEMO_MID_RATES: dict[str, float] = {
    "EUR": 4.9778,
    "USD": 4.6012,
    "GBP": 5.7845,
}

# Spread MaestroBank (procent) + comision fix (bani, RON) per valută demo.
DEMO_SPREAD_PERCENT: dict[str, float] = {
    "EUR": 0.35,
    "USD": 0.40,
    "GBP": 0.45,
}

DEMO_COMMISSION_MINOR: dict[str, int] = {
    "EUR": 1000,
    "USD": 1000,
    "GBP": 1200,
}

BASE_CURRENCY = "RON"
SUPPORTED_FOREIGN_CURRENCIES: list[str] = list(DEMO_MID_RATES.keys())
