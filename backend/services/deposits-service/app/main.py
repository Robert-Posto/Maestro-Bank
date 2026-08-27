"""deposits-service — depozite la termen (RON/EUR/USD/GBP), execuție reală
prin accounts-service.

Vezi docs/superpowers/specs/2026-08-27-deposits-design.md pentru design-ul
complet. Rate MaestroBank (politică proprie, NU feed extern) — vezi
app/rates.py.
"""

import logging

from fastapi import FastAPI

from app.database import close_database_connection, ping_database

logging.basicConfig(level=logging.INFO, format="%(asctime)s [deposits-service] %(levelname)s %(message)s")

app = FastAPI(title="MaestroBank Deposits Service")


@app.on_event("shutdown")
async def _shutdown() -> None:
    await close_database_connection()


@app.get("/health")
async def health_check():
    is_connected = await ping_database()
    return {
        "status": "ok" if is_connected else "error",
        "service": "deposits-service",
        "database": "connected" if is_connected else "disconnected",
    }
