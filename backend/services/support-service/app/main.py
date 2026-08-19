"""support-service — tichete de suport pentru utilizatori.

Rute reale sub /tickets — vezi routers/support.py. Fără AI (vezi task-ul
MaestroBank, secțiunea 20) — doar creare/listare/detaliu tichete.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import close_database_connection, ping_database
from app.routers.support import router as support_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [support-service] %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_database_connection()


app = FastAPI(title="MaestroBank Support Service", lifespan=lifespan)
app.include_router(support_router)


@app.get("/health")
async def health_check():
    is_connected = await ping_database()
    return {
        "status": "ok" if is_connected else "error",
        "service": "support-service",
        "database": "connected" if is_connected else "disconnected",
    }
