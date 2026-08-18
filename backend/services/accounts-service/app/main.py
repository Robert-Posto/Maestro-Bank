"""accounts-service — conturi, IBAN, solduri, carduri.

Rute publice (health) + protejate JWT (me, cards, dev/fund, {id}) +
interne (provisioning, transfer — vezi routers/internal.py, NU expuse
prin Gateway).
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import close_database_connection, ping_database
from app.routers.accounts import router as accounts_router
from app.routers.internal import router as internal_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [accounts-service] %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_database_connection()


app = FastAPI(title="MaestroBank Accounts Service", lifespan=lifespan)


@app.get("/health")
async def health_check():
    is_connected = await ping_database()
    return {
        "status": "ok" if is_connected else "error",
        "service": "accounts-service",
        "database": "connected" if is_connected else "disconnected",
    }


# Ordine importantă: /health (mai sus) și rutele literale (/me, /me/cards,
# în routers/accounts.py) trebuie înregistrate ÎNAINTE de wildcard-ul
# /{account_id}, altfel acesta le-ar "înghiți" pe toate (orice segment
# unic, inclusiv "health", ar fi interpretat ca account_id).
app.include_router(accounts_router)
app.include_router(internal_router)
