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
from app.routers.beneficiaries import router as beneficiaries_router
from app.routers.cards import router as cards_router
from app.routers.internal import router as internal_router
from app.routers.pockets import router as pockets_router

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


# Ordine importantă: /health (mai sus), /cards/* și /beneficiaries*
# trebuie înregistrate ÎNAINTE de accounts_router (care conține
# GET /{account_id} la rădăcină, UN SINGUR segment) — altfel acesta le-ar
# "înghiți" pe cele cu un singur segment (ex. GET /beneficiaries ar fi
# interpretat ca account_id="beneficiaries", FastAPI potrivind rutele în
# ordinea înregistrării). /cards/{id}/freeze etc. au 3+ segmente, deci nu
# sunt de fapt ambigue cu /{account_id} — dar păstrăm ordinea oricum,
# pentru claritate și siguranță pe termen lung.
app.include_router(cards_router)
app.include_router(beneficiaries_router)
app.include_router(pockets_router)
app.include_router(accounts_router)
app.include_router(internal_router)
