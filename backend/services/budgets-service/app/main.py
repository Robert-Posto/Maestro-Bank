"""budgets-service — bugete, abonamente, limite de cheltuieli.

Rute reale sub /budgets (bugete) și /subscriptions (abonamente) — vezi
routers/budgets.py, routers/subscriptions.py. Ruta internă
/internal/budgets/subscriptions/by-user/{id} e folosită DOAR de
transactions-service (forecast), NU e expusă prin Gateway.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import close_database_connection, ping_database
from app.routers.budgets import router as budgets_router
from app.routers.internal import router as internal_router
from app.routers.subscriptions import router as subscriptions_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [budgets-service] %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_database_connection()


app = FastAPI(title="MaestroBank Budgets Service", lifespan=lifespan)

app.include_router(budgets_router)
app.include_router(subscriptions_router)
app.include_router(internal_router)


@app.get("/health")
async def health_check():
    is_connected = await ping_database()
    return {
        "status": "ok" if is_connected else "error",
        "service": "budgets-service",
        "database": "connected" if is_connected else "disconnected",
    }
