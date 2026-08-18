"""Conexiunea la MongoDB pentru auth-service.

Folosește exclusiv baza `auth_db` (izolată de celelalte servicii — vezi
MONGO_URL din docker-compose.yml). Niciun alt microserviciu nu trebuie să
citească direct din această bază; accesul se face doar prin API-ul
auth-service.
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
