"""
Recreează clientul Motor pentru FIECARE test, legat de event loop-ul
curent al testului respectiv.

De ce: `app/database.py` creează clientul Motor o singură dată, la
importul modulului (înainte ca pytest-asyncio să fi pornit loop-ul unui
test). Motor/PyMongo nu permit reutilizarea unei conexiuni create pe un
alt event loop decât cel activ acum ("attached to a different loop") —
de-aia recreăm clientul aici, în fiecare test, în loop-ul corect.
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
