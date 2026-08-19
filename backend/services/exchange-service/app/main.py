"""exchange-service — motor de schimb valutar DEMO.

⚠️ NU e o integrare FX reală (vezi app/config.py). Rute reale sub
/exchange — vezi routers/exchange.py.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import close_database_connection, ping_database
from app.routers.exchange import router as exchange_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [exchange-service] %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_database_connection()


app = FastAPI(title="MaestroBank Exchange Service (DEMO)", lifespan=lifespan)
app.include_router(exchange_router)


@app.get("/health")
async def health_check():
    is_connected = await ping_database()
    return {
        "status": "ok" if is_connected else "error",
        "service": "exchange-service",
        "database": "connected" if is_connected else "disconnected",
    }
