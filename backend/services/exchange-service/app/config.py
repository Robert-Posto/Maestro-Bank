"""Configurație pentru exchange-service.

Cursul de bază (mid_rate) e REAL — preluat zilnic de la Banca Națională a
României (vezi app/bnr_rates.py), NU e hardcodat. Spread-ul și comisionul
rămân o politică SIMULATĂ MaestroBank (nicio bancă reală nu publică
propriul spread) — exact cum face și un neobank real: ia un curs de
referință public + aplică propria marjă. Execuția schimbului (POST
/exchange/execute) chiar mută solduri acum, între contul RON al userului
și contul lui pe valuta respectivă (eur/usd/gbp) — vezi app/service.py și
accounts-service/app/service.py::apply_internal_exchange.

`DEMO_MID_RATES` de mai jos rămâne doar ca FALLBACK (folosit dacă feed-ul
BNR e indisponibil și nu avem încă niciun curs salvat în DB).
"""

import os

BASE_CURRENCY = "RON"


class Settings:
    mongo_url: str = os.getenv("MONGO_URL", "mongodb://localhost:27017/exchange_db")
    jwt_secret: str = os.getenv("JWT_SECRET", "change-me-in-development")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")

    # Cât de des reîmprospătăm cursul de la BNR. BNR publică o dată/zi
    # lucrătoare — verificăm mai des (implicit la 6h) ca să prindem rapid
    # publicarea zilei, fără să bombardăm feed-ul BNR inutil.
    rates_refresh_interval_seconds: int = int(os.getenv("RATES_REFRESH_INTERVAL_SECONDS", str(6 * 60 * 60)))

    # Adresă INTERNĂ Docker — execuția schimbului cere accounts-service să
    # debiteze/crediteze efectiv (vezi /internal/accounts/exchange, NEexpus
    # prin Gateway, la fel ca restul rutelor /internal/*).
    accounts_service_url: str = os.getenv("ACCOUNTS_SERVICE_URL", "http://accounts-service:8000")


settings = Settings()

# Feed XML public, oficial, gratuit al BNR — nu e secret, nu necesită API key.
# NOTĂ: BNR a mutat acest feed pe subdomeniul curs.bnr.ro — vechea adresă
# (www.bnr.ro/nbrfxrates.xml) dă acum redirect către homepage, nu XML.
# Dacă BNR își schimbă din nou structura site-ului, aici e singurul loc de
# actualizat (plus namespace-ul XML din app/bnr_rates.py, dacă se schimbă și el).
BNR_RATES_URL = "https://curs.bnr.ro/nbrfxrates.xml"

# FALLBACK — folosit DOAR dacă feed-ul BNR e indisponibil și nu există
# încă niciun curs salvat în exchange_db.daily_rates. Valori aproximative,
# neactualizate automat.
DEMO_MID_RATES: dict[str, float] = {
    "EUR": 4.9778,
    "USD": 4.6012,
    "GBP": 5.7845,
}

# Spread MaestroBank (procent) + comision fix (bani, RON) per valută —
# politică SIMULATĂ, intenționat, indiferent de sursa cursului de bază.
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

SUPPORTED_FOREIGN_CURRENCIES: list[str] = list(DEMO_MID_RATES.keys())
