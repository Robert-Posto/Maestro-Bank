"""transactions-service — tranzacții, istoric, transferuri.

Rute reale sub prefix /transactions (transfers, listă, detaliu) — vezi
routers/transfers.py. Nu citește niciodată direct accounts_db.

La startup pornește și un loop intern (app/scheduler.py) care execută
transferurile programate scadente — vezi routers/scheduled_transfers.py.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import close_database_connection, ping_database
from app.routers.scheduled_transfers import router as scheduled_transfers_router
from app.routers.transfers import router as transfers_router
from app.scheduler import scheduled_transfers_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s [transactions-service] %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(scheduled_transfers_loop())
    yield
    task.cancel()
    await close_database_connection()


app = FastAPI(title="MaestroBank Transactions Service", lifespan=lifespan)
app.include_router(scheduled_transfers_router)
app.include_router(transfers_router)


@app.get("/health")
async def health_check():
    is_connected = await ping_database()
    return {
        "status": "ok" if is_connected else "error",
        "service": "transactions-service",
        "database": "connected" if is_connected else "disconnected",
    }
