"""transactions-service — tranzacții, istoric, transferuri.

Rute reale sub prefix /transactions (transfers, listă, detaliu) — vezi
routers/transfers.py. Nu citește niciodată direct accounts_db.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import close_database_connection, ping_database
from app.routers.transfers import router as transfers_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [transactions-service] %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_database_connection()


app = FastAPI(title="MaestroBank Transactions Service", lifespan=lifespan)
app.include_router(transfers_router)


@app.get("/health")
async def health_check():
    is_connected = await ping_database()
    return {
        "status": "ok" if is_connected else "error",
        "service": "transactions-service",
        "database": "connected" if is_connected else "disconnected",
    }
