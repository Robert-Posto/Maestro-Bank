"""Conexiunea la MongoDB pentru transactions-service.

Folosește exclusiv baza `tx_db`. Colecția `transactions` este rezervată
pentru istoricul de tranzacții (neimplementat încă). Acest serviciu NU
trebuie să citească direct din accounts_db — dacă are nevoie de date
despre conturi, le cere prin API-ul accounts-service (prin Gateway).
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
