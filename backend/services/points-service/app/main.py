"""points-service — puncte de loialitate, recompense curatoriate și roata
norocului, alimentate de plățile către comercianți (transferuri către un
cont FĂRĂ user MaestroBank real atașat — semnalul deja folosit de
transactions-service pentru exact asta).

Rate de câștig, catalogul de recompense și segmentele roții sunt politică
PROPRIE MaestroBank (nu un feed extern) — vezi app/earn_rates.py,
app/rewards_catalog.py, app/wheel_segments.py.

Fără scheduler — nicio treabă periodică (fără limită lunară la învârtirea
roții; disponibilă oricând userul are puncte suficiente — vezi
docs/superpowers/specs pentru raționament).
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import close_database_connection, ping_database
from app.i18n import LanguageMiddleware
from app.routers.internal import router as internal_router
from app.routers.points import router as points_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [points-service] %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_database_connection()


app = FastAPI(title="MaestroBank Points Service", lifespan=lifespan)
app.add_middleware(LanguageMiddleware)
app.include_router(points_router)
app.include_router(internal_router)


@app.get("/health")
async def health_check():
    is_connected = await ping_database()
    return {
        "status": "ok" if is_connected else "error",
        "service": "points-service",
        "database": "connected" if is_connected else "disconnected",
    }
