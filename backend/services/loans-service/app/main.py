"""loans-service — credite personale, execuție reală prin accounts-service.

Vezi docs/superpowers/specs/2026-08-27-credite-design.md pentru design-ul
complet. Dobânzi MaestroBank (politică proprie, NU feed extern) — vezi
app/rates.py. Eligibilitate calculată din istoricul REAL de venituri al
userului — vezi app/eligibility.py. Rată automată lunară + plată anticipată
— vezi app/scheduler.py / app/service.py.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import close_database_connection, ping_database
from app.i18n import LanguageMiddleware
from app.routers.loans import router as loans_router
from app.scheduler import payment_due_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s [loans-service] %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(payment_due_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await close_database_connection()


app = FastAPI(title="MaestroBank Loans Service", lifespan=lifespan)
app.add_middleware(LanguageMiddleware)
app.include_router(loans_router)


@app.get("/health")
async def health_check():
    is_connected = await ping_database()
    return {
        "status": "ok" if is_connected else "error",
        "service": "loans-service",
        "database": "connected" if is_connected else "disconnected",
    }
