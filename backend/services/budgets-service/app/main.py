"""budgets-service — bugete, abonamente, limite de cheltuieli (viitor).

În acest pas doar health check + conexiunea la budgets_db. Nu
implementăm încă business logic de bugete.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import close_database_connection, ping_database

logging.basicConfig(level=logging.INFO, format="%(asctime)s [budgets-service] %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_database_connection()


app = FastAPI(title="MaestroBank Budgets Service", lifespan=lifespan)


@app.get("/health")
async def health_check():
    is_connected = await ping_database()
    return {
        "status": "ok" if is_connected else "error",
        "service": "budgets-service",
        "database": "connected" if is_connected else "disconnected",
    }
