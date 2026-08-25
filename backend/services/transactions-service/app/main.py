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
from app.fraud.indexes import ensure_fraud_indexes
from app.holds import ensure_hold_indexes
from app.routers.internal import router as internal_router
from app.routers.internal import transactions_router as internal_transactions_router
from app.routers.scheduled_transfers import router as scheduled_transfers_router
from app.routers.staff import router as staff_router
from app.routers.transfers import router as transfers_router
from app.scheduler import hold_expiry_loop, scheduled_transfers_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s [transactions-service] %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Indexare idempotentă — nu există migrări în acest proiect (Mongo, nu
    # SQL), vezi auth-service::ensure_webauthn_indexes pentru același
    # pattern. ÎNAINTE de pornirea oricărui loop — acelea reutilizează
    # create_transfer/citesc db.transactions (vezi service.py, holds.py),
    # deci indexurile trebuie să existe înaintea oricărui transfer.
    await ensure_fraud_indexes()
    await ensure_hold_indexes()
    scheduled_transfers_task = asyncio.create_task(scheduled_transfers_loop())
    hold_expiry_task = asyncio.create_task(hold_expiry_loop())
    yield
    scheduled_transfers_task.cancel()
    # hold_expiry_loop atinge bani reali — oprire cu grijă (așteptăm task-ul,
    # nu doar cancel() fire-and-forget), ca un shutdown să nu întrerupă o
    # rezolvare de hold la jumătate. Vezi app/scheduler.py.
    hold_expiry_task.cancel()
    try:
        await hold_expiry_task
    except asyncio.CancelledError:
        pass
    await close_database_connection()


app = FastAPI(title="MaestroBank Transactions Service", lifespan=lifespan)
app.include_router(scheduled_transfers_router)
app.include_router(transfers_router)
app.include_router(staff_router)
app.include_router(internal_router)
app.include_router(internal_transactions_router)


@app.get("/health")
async def health_check():
    is_connected = await ping_database()
    return {
        "status": "ok" if is_connected else "error",
        "service": "transactions-service",
        "database": "connected" if is_connected else "disconnected",
    }
