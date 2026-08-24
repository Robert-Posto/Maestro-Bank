"""Conexiunea la MongoDB pentru exchange-service.

Folosește exclusiv baza `exchange_db`. Colecția `demo_exchanges` reține
istoricul schimburilor valutare EXECUTATE (POST /exchange/execute) — numele
colecției a rămas din faza inițială (doar simulare), dar solduri chiar se
mută acum, prin accounts-service — vezi app/service.py::execute_exchange.
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings

client: AsyncIOMotorClient = AsyncIOMotorClient(settings.mongo_url)
database: AsyncIOMotorDatabase = client.get_default_database()


def get_database() -> AsyncIOMotorDatabase:
    return database


async def ping_database() -> bool:
    try:
        await client.admin.command("ping")
        return True
    except Exception:
        return False


async def close_database_connection() -> None:
    client.close()
