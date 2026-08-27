"""deposits-service — depozite la termen (RON/EUR/USD/GBP), execuție reală
prin accounts-service.

Vezi docs/superpowers/specs/2026-08-27-deposits-design.md pentru design-ul
complet. Rate MaestroBank (politică proprie, NU feed extern) — vezi
app/rates.py. Reînnoire/plată automată la scadență — vezi app/scheduler.py.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import close_database_connection, ping_database
from app.routers.deposits import router as deposits_router
from app.scheduler import maturity_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s [deposits-service] %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(maturity_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await close_database_connection()


app = FastAPI(title="MaestroBank Deposits Service", lifespan=lifespan)
app.include_router(deposits_router)


@app.get("/health")
async def health_check():
    is_connected = await ping_database()
    return {
        "status": "ok" if is_connected else "error",
        "service": "deposits-service",
        "database": "connected" if is_connected else "disconnected",
    }
