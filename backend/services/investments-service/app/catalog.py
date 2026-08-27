"""Catalogul de instrumente tranzacționabile — MaestroBank ofertă
CURATORIATĂ, fixă (16 simboluri), NU o piață deschisă unde userul poate
căuta orice simbol — la fel ca tabelul de rate de la Depozite. Toate se
tranzacționează în USD (vezi app/service.py — contul USD al userului,
deja existent, e reutilizat exact ca la Schimb valutar).

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

SYMBOLS: list[str] = list(CATALOG.keys())


def is_valid_symbol(symbol: str) -> bool:
    return symbol in CATALOG


def name_for(symbol: str) -> str:
    return CATALOG.get(symbol, symbol)
