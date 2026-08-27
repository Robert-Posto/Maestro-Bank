"""Conexiunea la MongoDB pentru ai-orchestrator-service.

Primul database.py al acestui serviciu — până acum era complet stateless
(vezi comentariile din app/models/spending_forecast.py și
app/models/support.py despre "fără memorie pe termen lung", o decizie
inversată explicit pentru persistența conversațiilor, vezi
docs/superpowers/specs/2026-08-26-persistent-chat-history-design.md).
Folosește exclusiv baza `ai_orchestrator_db`, colecția `conversations`
(vezi app/services/conversation_service.py).
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
