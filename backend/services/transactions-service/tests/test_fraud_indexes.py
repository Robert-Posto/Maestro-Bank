"""Teste cu Mongo real pentru indexarea idempotentă din app/fraud/indexes.py
— vezi app/main.py::lifespan (apelată la fiecare pornire, nu doar o dată)."""

import pytest

from app.database import get_database
from app.fraud.indexes import ensure_fraud_indexes

pytestmark = pytest.mark.asyncio


async def test_ensure_fraud_indexes_is_idempotent():
    await ensure_fraud_indexes()
    await ensure_fraud_indexes()  # a doua rulare NU trebuie să arunce nimic

    db = get_database()
    profile_index_names = set((await db.fraud_profiles.index_information()).keys())
    evaluation_index_names = set((await db.fraud_evaluations.index_information()).keys())
    transaction_index_names = set((await db.transactions.index_information()).keys())

    assert "user_id_1" in profile_index_names
    assert "transaction_id_1" in evaluation_index_names
    assert "user_id_1_evaluated_at_-1" in evaluation_index_names
    assert "evaluated_at_-1_score_1" in evaluation_index_names
    assert "status_1" in evaluation_index_names
    assert "from_account_id_1_created_at_-1" in transaction_index_names
    assert "to_account_id_1_created_at_-1" in transaction_index_names
    assert "from_account_id_1_to_iban_1_created_at_-1" in transaction_index_names


async def test_fraud_profiles_user_id_index_is_unique():
    await ensure_fraud_indexes()
    db = get_database()
    info = await db.fraud_profiles.index_information()
    assert info["user_id_1"]["unique"] is True


async def test_fraud_evaluations_transaction_id_index_is_unique():
    await ensure_fraud_indexes()
    db = get_database()
    info = await db.fraud_evaluations.index_information()
    assert info["transaction_id_1"]["unique"] is True
