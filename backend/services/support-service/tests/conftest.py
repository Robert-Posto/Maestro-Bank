"""Vezi backend/services/auth-service/tests/conftest.py pentru explicația
completă — recreăm clientul Motor per test, legat de event loop-ul curent.
"""

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

import app.database as db_module
from app.config import settings


@pytest.fixture(autouse=True)
async def fresh_database():
    db_module.client = AsyncIOMotorClient(settings.mongo_url)
    db_module.database = db_module.client.get_default_database()
    yield
    db_module.client.close()
