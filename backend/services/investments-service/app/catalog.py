"""Catalogul de instrumente — MaestroBank ofertă CURATORIATĂ, fixă, NU o
piață deschisă unde userul poate căuta orice simbol — la fel ca tabelul de
rate de la Depozite.

Două categorii, tratate diferit:
  - CATALOG (16 acțiuni/ETF-uri) — TRANZACȚIONABILE, toate în USD (vezi
    app/service.py — contul USD al userului, deja existent, reutilizat
    exact ca la Schimb valutar).
  - INDICES (6 indici bursieri reali) — DOAR informative, ca la orice
    aplicație de bancă/brokeraj reală ("piețele azi") — un indice nu se
    cumpără direct (SPY/QQQ, deja în catalog, sunt ETF-urile care-l
    urmăresc, alea CHIAR se tranzacționează).

`name`-urile sunt informative (afișate în UI) — prețul REAL vine live de
la Yahoo (vezi app/prices.py), nu e hardcodat aici.
"""

CATALOG: dict[str, str] = {
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corporation",
    "GOOGL": "Alphabet Inc.",
    "AMZN": "Amazon.com Inc.",
    "TSLA": "Tesla Inc.",
    "NVDA": "NVIDIA Corporation",
    "META": "Meta Platforms Inc.",
    "NFLX": "Netflix Inc.",
    "DIS": "The Walt Disney Company",
    "JPM": "JPMorgan Chase & Co.",
    "V": "Visa Inc.",
    "KO": "The Coca-Cola Company",
    "BRK-B": "Berkshire Hathaway Inc. (B)",
    "SPY": "SPDR S&P 500 ETF Trust",
    "QQQ": "Invesco QQQ Trust (Nasdaq 100)",
    "IWM": "iShares Russell 2000 ETF",
}

# Indici bursieri reali — DOAR informativ (vezi docstring-ul modulului).
INDICES: dict[str, str] = {
    "^GSPC": "S&P 500",
    "^DJI": "Dow Jones Industrial Average",
    "^IXIC": "NASDAQ Composite",
    "^VIX": "CBOE Volatility Index",
    "^STOXX50E": "EURO STOXX 50",
    "^FTSE": "FTSE 100",
}

SYMBOLS: list[str] = list(CATALOG.keys())
INDEX_SYMBOLS: list[str] = list(INDICES.keys())
ALL_SYMBOLS: list[str] = SYMBOLS + INDEX_SYMBOLS


def is_valid_symbol(symbol: str) -> bool:
    """TRANZACȚIONABIL — doar catalogul de acțiuni/ETF-uri, NU indicii."""
    return symbol in CATALOG


def is_known_symbol(symbol: str) -> bool:
    """Cunoscut de MaestroBank — acțiune/ETF SAU indice — pentru vizualizarea
    de detalii (click), care e permisă și pe indici, deși nu sunt tranzacționabili."""
    return symbol in CATALOG or symbol in INDICES


def name_for(symbol: str) -> str:
    return CATALOG.get(symbol) or INDICES.get(symbol, symbol)
