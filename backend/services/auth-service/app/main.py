"""auth-service — users, autentificare, JWT, hashing parole (bcrypt).

Responsabilități actuale: register / login / me. NU implementează încă
OAuth, MFA sau integrare bancară reală.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import service, webauthn_service
from app.database import close_database_connection, ping_database
from app.login_events import ensure_login_event_indexes
from app.routers.auth import router as auth_router
from app.routers.internal import router as internal_router
from app.routers.webauthn import router as webauthn_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [auth-service] %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Indexare idempotentă — nu există migrări în acest proiect (Mongo,
    # nu SQL), vezi accounts-service::backfill_missing_account_types
    # pentru același pattern.
    await webauthn_service.ensure_webauthn_indexes()
    await service.backfill_verification_flags()
    await ensure_login_event_indexes()
    yield
    await close_database_connection()


app = FastAPI(title="MaestroBank Auth Service", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(webauthn_router)
app.include_router(internal_router)


@app.get("/health")
async def health_check():
    is_connected = await ping_database()
    return {
        "status": "ok" if is_connected else "error",
        "service": "auth-service",
        "database": "connected" if is_connected else "disconnected",
    }
