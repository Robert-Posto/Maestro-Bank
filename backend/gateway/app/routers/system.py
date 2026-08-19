"""GET /api/system/health — status agregat al arhitecturii.

Verifică MongoDB (direct) + fiecare microserviciu (prin /health-ul lui).
Nu blochează întregul răspuns dacă un serviciu nu răspunde — raportează
clar starea fiecăruia, cu timeout scurt per serviciu.
"""

import asyncio
import logging

import httpx
from fastapi import APIRouter
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings

logger = logging.getLogger("gateway")

router = APIRouter()

_SERVICE_HEALTH_URLS: dict[str, str] = {
    "auth": f"{settings.auth_service_url}/health",
    "accounts": f"{settings.accounts_service_url}/health",
    "transactions": f"{settings.transactions_service_url}/health",
    "budgets": f"{settings.budgets_service_url}/health",
    "support": f"{settings.support_service_url}/health",
    "exchange": f"{settings.exchange_service_url}/health",
}

_mongo_client = AsyncIOMotorClient(settings.mongo_url)


async def _check_mongodb() -> str:
    try:
        await _mongo_client.admin.command("ping")
        return "connected"
    except Exception:
        return "disconnected"


async def _check_service(name: str, url: str) -> tuple[str, str]:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(url)
        if response.status_code == 200:
            body = response.json()
            return name, body.get("database", "connected")
        return name, f"error (HTTP {response.status_code})"
    except httpx.RequestError:
        logger.warning("gateway: serviciul '%s' nu răspunde la %s", name, url)
        return name, "unreachable"


@router.get("/api/system/health")
async def system_health():
    mongodb_status, service_results = await asyncio.gather(
        _check_mongodb(),
        asyncio.gather(*(_check_service(name, url) for name, url in _SERVICE_HEALTH_URLS.items())),
    )

    services = dict(service_results)
    all_connected = mongodb_status == "connected" and all(status == "connected" for status in services.values())

    return {
        "status": "ok" if all_connected else "degraded",
        "mongodb": mongodb_status,
        "services": services,
    }
