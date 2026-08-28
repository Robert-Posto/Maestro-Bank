"""Conexiunea la MongoDB pentru loans-service. Folosește exclusiv baza
`loans_db`, colecțiile `loans` și `loan_payments`."""

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
