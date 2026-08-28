"""support-service — tichete de suport, notificări, documente de semnat
(eSign) pentru utilizatori.

Rute reale sub /tickets — vezi routers/support.py; /documents — vezi
routers/documents.py (client) și routers/staff.py (personal).
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import close_database_connection, ping_database
from app.i18n import LanguageMiddleware
from app.routers.documents import router as documents_router
from app.routers.notifications import internal_router as notifications_internal_router
from app.routers.notifications import router as notifications_router
from app.routers.staff import router as staff_router
from app.routers.support import router as support_router
from app.service import ensure_document_indexes

logging.basicConfig(level=logging.INFO, format="%(asctime)s [support-service] %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_document_indexes()
    yield
    await close_database_connection()


app = FastAPI(title="MaestroBank Support Service", lifespan=lifespan)
app.add_middleware(LanguageMiddleware)
app.include_router(support_router)
app.include_router(notifications_router)
app.include_router(notifications_internal_router)
app.include_router(documents_router)
app.include_router(staff_router)


@app.get("/health")
async def health_check():
    is_connected = await ping_database()
    return {
        "status": "ok" if is_connected else "error",
        "service": "support-service",
        "database": "connected" if is_connected else "disconnected",
    }
