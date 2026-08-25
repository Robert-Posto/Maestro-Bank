"""Vezi backend/services/auth-service/tests/conftest.py pentru explicația
completă — recreăm clientul Motor per test, legat de event loop-ul curent.
"""

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

import app.database as db_module
from app.config import settings
from app.guardian import llm_client


@pytest.fixture(autouse=True)
def no_real_guardian_llm_calls(monkeypatch):
    """Testele rulează în ACELAȘI container ca aplicația reală — dacă
    .env are credențiale Azure OpenAI reale (pentru verificare manuală
    live), fără gardă, orice test care trece prin create_transfer ar
    declanșa un apel HTTP REAL către Azure, lent și nedeterminist,
    indiferent de fișierul de test.

    Blocăm la nivelul `_get_chat_client` (simulăm "neconfigurat" —
    `complete_json` cade deja curat pe None, fără rețea, exact cum face
    și fără credențiale reale), NU la nivelul `complete_json` însuși —
    altfel test_guardian_llm_client.py, care testează chiar
    `complete_json`, ar deveni imposibil de testat. Un test care vrea
    explicit clientul fals (test_guardian_llm_client.py) sau un răspuns
    LLM controlat (test_guardian_service.py) își suprascrie propriul
    monkeypatch peste acesta, executat ulterior în corpul testului."""
    monkeypatch.setattr(llm_client, "_get_chat_client", lambda: None)


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
