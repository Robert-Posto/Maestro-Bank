"""Conexiunea la MongoDB pentru accounts-service.

Folosește exclusiv baza `accounts_db`. Colecțiile `accounts` și `cards`
sunt rezervate pentru logica bancară reală (neimplementată încă) —
MongoDB le va crea automat la prima scriere, nu e nevoie să le pregătim
explicit. Niciun alt microserviciu nu trebuie să citească direct din
această bază.
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
