"""exchange-service — motor de schimb valutar cu curs REAL (BNR) + politică
de business SIMULATĂ (spread/comision, execuție fără mutare reală de fonduri).

Vezi app/config.py și app/bnr_rates.py pentru sursa cursului. Rute reale
sub /exchange — vezi routers/exchange.py.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.database import close_database_connection, ping_database
from app.i18n import LanguageMiddleware
from app.routers.exchange import router as exchange_router
from app.routers.internal import router as internal_router
from app.service import refresh_rates_from_bnr

logging.basicConfig(level=logging.INFO, format="%(asctime)s [exchange-service] %(levelname)s %(message)s")
logger = logging.getLogger("exchange-service")


async def _rates_refresh_loop() -> None:
    """Reîmprospătează cursul BNR imediat la pornire, apoi periodic.

    Rulează ca task de fundal, NU blochează pornirea serverului — dacă
    primul fetch eșuează (BNR jos, fără rețea etc.), aplicația tot pornește
    normal și cade pe fallback-ul demo (vezi app/service.py::_get_mid_rate)
    până la următoarea încercare reușită.
    """
    while True:
        await refresh_rates_from_bnr()
        await asyncio.sleep(settings.rates_refresh_interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    refresh_task = asyncio.create_task(_rates_refresh_loop())
    yield
    refresh_task.cancel()
    try:
        await refresh_task
    except asyncio.CancelledError:
        pass
    await close_database_connection()


app = FastAPI(title="MaestroBank Exchange Service", lifespan=lifespan)
app.add_middleware(LanguageMiddleware)
app.include_router(exchange_router)
app.include_router(internal_router)


@app.get("/health")
async def health_check():
    is_connected = await ping_database()
    return {
        "status": "ok" if is_connected else "error",
        "service": "exchange-service",
        "database": "connected" if is_connected else "disconnected",
    }
