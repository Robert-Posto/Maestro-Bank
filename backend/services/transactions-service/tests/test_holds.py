"""Teste pentru app/holds.py — ciclul de viață al unei rețineri. Apeluri
directe către modul (nu prin HTTP), cu accounts-service/auth-service
mock-uite — la fel ca test_transfers.py mock-uiește accounts-service prin
app.service._get_account_by_user etc.

fresh_database / clean_fraud_collections (conftest.py) se aplică automat.
tx_db.transactions e propriu acestui fișier (autouse local, mai jos).
"""

from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId
from fastapi import HTTPException

from app import holds
from app.database import get_database

pytestmark = pytest.mark.asyncio

HOLDING_ACCOUNT_ID = str(ObjectId())
SOURCE_ACCOUNT_ID = str(ObjectId())
DEST_ACCOUNT_ID = str(ObjectId())


@pytest.fixture(autouse=True)
async def clean_transactions():
    await get_database().transactions.delete_many({})
    yield
    await get_database().transactions.delete_many({})


@pytest.fixture
def mock_ledger(monkeypatch):
    """Simulează accounts-service: un dict simplu account_id -> balance_minor,
    mutat de _apply_ledger_transfer exact ca apply_internal_transfer real
    (debit condiționat de sold suficient)."""
    balances = {SOURCE_ACCOUNT_ID: 100_000, HOLDING_ACCOUNT_ID: 0, DEST_ACCOUNT_ID: 0}

    async def fake_resolve_holding_account_id() -> str:
        return HOLDING_ACCOUNT_ID

    async def fake_apply_ledger_transfer(from_account_id: str, to_account_id: str, amount_minor: int) -> bool:
        if balances.get(from_account_id, 0) < amount_minor:
            return False
        balances[from_account_id] -= amount_minor
        balances[to_account_id] = balances.get(to_account_id, 0) + amount_minor
        return True

    monkeypatch.setattr("app.holds._resolve_holding_account_id", fake_resolve_holding_account_id)
    monkeypatch.setattr("app.holds._apply_ledger_transfer", fake_apply_ledger_transfer)
    return balances


async def _seed_pending_transaction(**overrides) -> dict:
    now = datetime.now(timezone.utc)
    base = {
        "from_account_id": SOURCE_ACCOUNT_ID,
        "to_account_id": DEST_ACCOUNT_ID,
        "from_iban": "RO11MAES0000000000000001",
        "to_iban": "RO22MAES0000000000000002",
        "from_name": "Sursa Test",
        "to_name": "Destinatie Test",
        "amount_minor": 90_000,
        "currency": "RON",
        "description": "",
        "category": "other",
        "type": "transfer",
        "status": "pending",
        "recognized": False,
        "reported": False,
        "created_at": now,
    }
    base.update(overrides)
    result = await get_database().transactions.insert_one(base)
    base["_id"] = result.inserted_id
    return base


async def _create_hold_for(tx: dict, mock_ledger: dict) -> None:
    await holds.create_hold(
        transaction_id=tx["_id"],
        source_account_id=tx["from_account_id"],
        amount_minor=tx["amount_minor"],
        evaluated_at=datetime.now(timezone.utc),
    )


# --- create_hold ------------------------------------------------------


async def test_create_hold_debits_source_and_sets_pending_review(mock_ledger):
    tx = await _seed_pending_transaction()
    await _create_hold_for(tx, mock_ledger)

    assert mock_ledger[SOURCE_ACCOUNT_ID] == 10_000  # 100_000 - 90_000
    assert mock_ledger[HOLDING_ACCOUNT_ID] == 90_000

    stored = await get_database().transactions.find_one({"_id": tx["_id"]})
    assert stored["status"] == "pending_review"
    assert stored["hold"]["holding_account_id"] == HOLDING_ACCOUNT_ID
    assert stored["hold"]["resolution"] is None


async def test_create_hold_raises_on_insufficient_balance(mock_ledger):
    tx = await _seed_pending_transaction(amount_minor=999_999)
    with pytest.raises(HTTPException) as exc_info:
        await _create_hold_for(tx, mock_ledger)
    assert exc_info.value.status_code == 409

    # niciun ban nu s-a mișcat
    assert mock_ledger[SOURCE_ACCOUNT_ID] == 100_000
    stored = await get_database().transactions.find_one({"_id": tx["_id"]})
    assert stored["status"] == "pending"  # neschimbat de holds.py — service.py e cel care marchează "failed"


# --- resolve_hold: approve / reject / cancel ---------------------------


async def test_approve_hold_releases_to_destination(mock_ledger):
    tx = await _seed_pending_transaction()
    await _create_hold_for(tx, mock_ledger)

    result = await holds.approve_hold(str(tx["_id"]), "staff-1")

    assert result["status"] == "completed"
    assert result["hold"]["resolution"] == "released"
    assert result["hold"]["resolved_by"] == "staff-1"
    assert mock_ledger[DEST_ACCOUNT_ID] == 90_000
    assert mock_ledger[HOLDING_ACCOUNT_ID] == 0


async def test_approve_hold_updates_fraud_profile(mock_ledger):
    """Un hold ELIBERAT e, la final, un transfer real, complet — profilul
    trebuie să-l vadă, altfel un user aprobat repetat ar rămâne prins
    la nesfârșit în cold-start-ul propriilor percentile."""
    tx = await _seed_pending_transaction(category="entertainment")
    await _create_hold_for(tx, mock_ledger)
    await get_database().fraud_evaluations.insert_one(
        {
            "transaction_id": tx["_id"],
            "user_id": "user-abc",
            "status": "ok",
            "score": 90,
            "fired_rules": [],
            "decision_would_apply": "hold",
            "ruleset_version": "test-1",
            "shadow_mode": False,
            "evaluated_at": datetime.now(timezone.utc),
            "error": None,
            "created_at": datetime.now(timezone.utc),
        }
    )

    await holds.approve_hold(str(tx["_id"]), "staff-1")

    profile = await get_database().fraud_profiles.find_one({"user_id": "user-abc"})
    assert profile is not None
    assert profile["transaction_count"] == 1
    assert profile["category_counts"] == {"entertainment": 1}


async def test_reject_hold_does_not_update_fraud_profile(mock_ledger):
    """Opusul testului de mai sus — o respingere NU e "comportament normal
    confirmat", nu trebuie să antreneze profilul."""
    tx = await _seed_pending_transaction()
    await _create_hold_for(tx, mock_ledger)
    await get_database().fraud_evaluations.insert_one(
        {
            "transaction_id": tx["_id"],
            "user_id": "user-xyz",
            "status": "ok",
            "score": 90,
            "fired_rules": [],
            "decision_would_apply": "hold",
            "ruleset_version": "test-1",
            "shadow_mode": False,
            "evaluated_at": datetime.now(timezone.utc),
            "error": None,
            "created_at": datetime.now(timezone.utc),
        }
    )

    await holds.reject_hold(str(tx["_id"]), "staff-1")

    assert await get_database().fraud_profiles.find_one({"user_id": "user-xyz"}) is None


async def test_reject_hold_reverses_to_source(mock_ledger):
    tx = await _seed_pending_transaction()
    await _create_hold_for(tx, mock_ledger)

    result = await holds.reject_hold(str(tx["_id"]), "staff-1")

    assert result["status"] == "cancelled"
    assert result["hold"]["resolution"] == "cancelled"
    assert mock_ledger[SOURCE_ACCOUNT_ID] == 100_000  # revenit integral
    assert mock_ledger[DEST_ACCOUNT_ID] == 0


async def test_cancel_hold_by_customer_reverses_to_source(mock_ledger):
    tx = await _seed_pending_transaction()
    await _create_hold_for(tx, mock_ledger)

    result = await holds.cancel_hold(str(tx["_id"]))

    assert result["status"] == "cancelled"
    assert result["hold"]["resolved_by"] == "customer"
    assert mock_ledger[SOURCE_ACCOUNT_ID] == 100_000


async def test_resolve_hold_nonexistent_transaction_404(mock_ledger):
    with pytest.raises(HTTPException) as exc_info:
        await holds.reject_hold(str(ObjectId()), "staff-1")
    assert exc_info.value.status_code == 404


async def test_resolve_hold_not_pending_review_409(mock_ledger):
    tx = await _seed_pending_transaction(status="completed")
    with pytest.raises(HTTPException) as exc_info:
        await holds.approve_hold(str(tx["_id"]), "staff-1")
    assert exc_info.value.status_code == 409


async def test_resolve_hold_twice_second_attempt_rejected_and_no_double_transfer(mock_ledger):
    """Cel mai important test de concurență: a doua rezolvare a ACELUIAȘI
    hold nu mișcă banii a doua oară, indiferent care cale ajunge a doua."""
    tx = await _seed_pending_transaction()
    await _create_hold_for(tx, mock_ledger)

    first = await holds.approve_hold(str(tx["_id"]), "staff-1")
    assert first["status"] == "completed"
    balance_after_first = dict(mock_ledger)

    with pytest.raises(HTTPException) as exc_info:
        await holds.reject_hold(str(tx["_id"]), "staff-2")
    assert exc_info.value.status_code == 409

    assert mock_ledger == balance_after_first  # nicio mișcare suplimentară de fonduri


# --- fallback / "stuck" -------------------------------------------------


async def test_approve_hold_falls_back_to_source_when_destination_unavailable(mock_ledger, monkeypatch):
    """Cel mai important test din acest fișier: dacă eliberarea către
    beneficiar eșuează (cont închis între timp), fondurile NU rămân blocate
    în contul de reținere — se întorc automat la expeditor."""
    tx = await _seed_pending_transaction()
    await _create_hold_for(tx, mock_ledger)

    real_transfer = holds._apply_ledger_transfer

    async def flaky_transfer(from_account_id: str, to_account_id: str, amount_minor: int) -> bool:
        if to_account_id == DEST_ACCOUNT_ID:
            return False  # beneficiarul a devenit indisponibil
        return await real_transfer(from_account_id, to_account_id, amount_minor)

    monkeypatch.setattr("app.holds._apply_ledger_transfer", flaky_transfer)

    result = await holds.approve_hold(str(tx["_id"]), "staff-1")

    assert result["status"] == "cancelled"
    assert result["hold"]["resolution"] == "expired"
    assert mock_ledger[SOURCE_ACCOUNT_ID] == 100_000  # fondurile s-au întors, NU au rămas în holding
    assert mock_ledger[HOLDING_ACCOUNT_ID] == 0
    assert mock_ledger[DEST_ACCOUNT_ID] == 0


async def test_approve_hold_marks_stuck_when_both_transfers_fail(mock_ledger, monkeypatch):
    tx = await _seed_pending_transaction()
    await _create_hold_for(tx, mock_ledger)

    async def always_fails(from_account_id: str, to_account_id: str, amount_minor: int) -> bool:
        return False

    monkeypatch.setattr("app.holds._apply_ledger_transfer", always_fails)

    with pytest.raises(HTTPException) as exc_info:
        await holds.approve_hold(str(tx["_id"]), "staff-1")
    assert exc_info.value.status_code == 502

    stored = await get_database().transactions.find_one({"_id": tx["_id"]})
    assert stored["status"] == "pending_review"  # NU marcat fals "completed"/"cancelled"
    assert stored["hold"]["resolution"] == "stuck"


# --- sweep_expired_holds -------------------------------------------------


async def test_sweep_resolves_only_expired_holds(mock_ledger):
    now = datetime.now(timezone.utc)
    expired_tx = await _seed_pending_transaction(amount_minor=10_000)
    fresh_tx = await _seed_pending_transaction(amount_minor=10_000)

    await _create_hold_for(expired_tx, mock_ledger)
    await _create_hold_for(fresh_tx, mock_ledger)
    await get_database().transactions.update_one(
        {"_id": expired_tx["_id"]}, {"$set": {"hold.expires_at": now - timedelta(hours=1)}}
    )
    await get_database().transactions.update_one(
        {"_id": fresh_tx["_id"]}, {"$set": {"hold.expires_at": now + timedelta(hours=23)}}
    )

    processed = await holds.sweep_expired_holds()
    assert processed == 1

    expired_stored = await get_database().transactions.find_one({"_id": expired_tx["_id"]})
    fresh_stored = await get_database().transactions.find_one({"_id": fresh_tx["_id"]})
    assert expired_stored["status"] == "cancelled"
    assert expired_stored["hold"]["resolution"] == "expired"
    assert expired_stored["hold"]["resolved_by"] == "system"
    assert fresh_stored["status"] == "pending_review"


async def test_sweep_is_idempotent(mock_ledger):
    tx = await _seed_pending_transaction(amount_minor=10_000)
    await _create_hold_for(tx, mock_ledger)
    await get_database().transactions.update_one(
        {"_id": tx["_id"]}, {"$set": {"hold.expires_at": datetime.now(timezone.utc) - timedelta(hours=1)}}
    )

    first_pass = await holds.sweep_expired_holds()
    second_pass = await holds.sweep_expired_holds()

    assert first_pass == 1
    assert second_pass == 0


# --- list_pending_holds ---------------------------------------------------


async def test_list_pending_holds_composes_score_and_contact(mock_ledger, monkeypatch):
    tx = await _seed_pending_transaction()
    await _create_hold_for(tx, mock_ledger)
    await get_database().fraud_evaluations.insert_one(
        {
            "transaction_id": tx["_id"],
            "user_id": "user-123",
            "status": "ok",
            "score": 92,
            "fired_rules": [{"rule_id": "AMT-04", "family": "amount", "weight": 40, "contribution": 40.0, "excluded_from_score": False, "values": {}}],
            "decision_would_apply": "hold",
            "ruleset_version": "test-1",
            "shadow_mode": False,
            "evaluated_at": datetime.now(timezone.utc),
            "error": None,
            "created_at": datetime.now(timezone.utc),
        }
    )

    async def fake_fetch_contact(user_id: str) -> dict | None:
        assert user_id == "user-123"
        return {"first_name": "Ana", "last_name": "Pop", "email": "ana@example.com", "phone_number": "+40700000000"}

    monkeypatch.setattr("app.holds._fetch_user_contact", fake_fetch_contact)

    result = await holds.list_pending_holds()

    assert len(result) == 1
    assert result[0]["id"] == str(tx["_id"])
    assert result[0]["score"] == 92
    assert result[0]["fired_rule_ids"] == ["AMT-04"]
    assert result[0]["customer"]["phone_number"] == "+40700000000"


async def test_list_pending_holds_composes_guardian_staff_explanation(mock_ledger, monkeypatch):
    """Vezi app/guardian/ — raportul AI pentru personal (guardian.
    staff_explanation, scris de generate_guardian_explanations) trebuie
    compus în lista de rețineri exact cum sunt deja score/fired_rule_ids."""
    tx = await _seed_pending_transaction()
    await _create_hold_for(tx, mock_ledger)
    await get_database().fraud_evaluations.insert_one(
        {
            "transaction_id": tx["_id"],
            "user_id": "user-123",
            "status": "ok",
            "score": 92,
            "fired_rules": [{"rule_id": "AMT-04", "family": "amount", "weight": 40, "contribution": 40.0, "excluded_from_score": False, "values": {}}],
            "decision_would_apply": "hold",
            "ruleset_version": "test-1",
            "shadow_mode": False,
            "evaluated_at": datetime.now(timezone.utc),
            "error": None,
            "created_at": datetime.now(timezone.utc),
            "guardian": {
                "status": "ready",
                "staff_explanation": "Scor 92/100 — golire de cont, prima plată către acest beneficiar.",
                "customer_tier": "held",
                "customer_phrase": "Tranzacția a fost reținută pentru verificare.",
                "source": "llm",
                "generated_at": datetime.now(timezone.utc),
                "model": "gpt-5-mini",
            },
        }
    )

    async def fake_fetch_contact(user_id: str) -> dict | None:
        return {"first_name": "Ana", "last_name": "Pop", "email": "ana@example.com", "phone_number": "+40700000000"}

    monkeypatch.setattr("app.holds._fetch_user_contact", fake_fetch_contact)

    result = await holds.list_pending_holds()

    assert len(result) == 1
    assert result[0]["guardian_staff_explanation"] == "Scor 92/100 — golire de cont, prima plată către acest beneficiar."


async def test_list_pending_holds_empty_when_none_pending(mock_ledger):
    assert await holds.list_pending_holds() == []
