"""investments-service — cumpărare/vânzare de acțiuni/ETF-uri (catalog
curatoriat, 16 simboluri, tranzacționate în USD), execuție reală prin
accounts-service.

Vezi docs/superpowers/specs/2026-08-27-investments-design.md pentru
design-ul complet. Preț NEOFICIAL (Yahoo Finance, nu există echivalent
gratuit oficial) — vezi app/prices.py. Reîmprospătare periodică — vezi
app/scheduler.py.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import close_database_connection, ping_database
from app.prices import refresh_all_prices
from app.routers.investments import router as investments_router
from app.scheduler import price_refresh_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s [investments-service] %(levelname)s %(message)s")
logger = logging.getLogger("investments-service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Reîmprospătare imediată la pornire (ca la exchange-service cu BNR) —
    # userul nu trebuie să aștepte primul ciclu de 15 min ca să vadă
    # prețuri reale. Best-effort — dacă eșuează, loop-ul de mai jos oricum
    # reîncearcă periodic; nu blocăm boot-ul serviciului pe asta.
    try:
        await refresh_all_prices()
    except Exception:
        logger.exception("investments-service: reîmprospătarea inițială de prețuri a eșuat")

    task = asyncio.create_task(price_refresh_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await close_database_connection()


app = FastAPI(title="MaestroBank Investments Service", lifespan=lifespan)
app.include_router(investments_router)


@app.get("/health")
async def health_check():
    is_connected = await ping_database()
    return {
        "status": "ok" if is_connected else "error",
        "service": "investments-service",
        "database": "connected" if is_connected else "disconnected",
    }
