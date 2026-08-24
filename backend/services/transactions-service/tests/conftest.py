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


@pytest.fixture(autouse=True)
async def clean_fraud_collections(fresh_database):
    """La fel ca `clean_transactions` din test_transfers.py, dar pentru
    colecțiile noi din app/fraud/ — comun tuturor fișierelor de test din
    acest director (nu doar test_transfers.py), de-aia trăiește în conftest.
    Depinde explicit de `fresh_database`, ca ordinea să nu se bazeze pe
    ordinea implicită de definire a fixture-urilor autouse."""
    db = db_module.database
    await db.fraud_profiles.delete_many({})
    await db.fraud_evaluations.delete_many({})
    await db.fraud_cohort_baseline.delete_many({})
    yield
    await db.fraud_profiles.delete_many({})
    await db.fraud_evaluations.delete_many({})
    await db.fraud_cohort_baseline.delete_many({})
