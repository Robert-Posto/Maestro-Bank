"""Teste pentru app/guardian/service.py — `compute_customer_risk` (pur) și
`generate_guardian_explanations` (scrie în DB, singurul loc cu voie să
atingă `guardian.*`/`risk.phrase`/`risk.status`).

Cel mai important test de aici e `test_adversarial_llm_response_cannot_
alter_other_fields` — probează garanția "Guardian nu poate NICIODATĂ
schimba decizia", nu doar politica declarată."""

from datetime import datetime, timezone

import pytest
from bson import ObjectId

from app.database import get_database
from app.guardian import service as guardian_service
from app.guardian.templates import HELD_CUSTOMER_PHRASE, SAFE_CUSTOMER_PHRASE

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def clean_transactions():
    await get_database().transactions.delete_many({})
    yield
    await get_database().transactions.delete_many({})


# --- compute_customer_risk (pur, fără DB, fără LLM) -------------------------


async def test_compute_customer_risk_pass_band_is_safe():
    risk = guardian_service.compute_customer_risk(None, is_held=False)
    assert risk == {"tier": "safe", "phrase": SAFE_CUSTOMER_PHRASE, "status": "ready"}
    assert guardian_service.compute_customer_risk("pass", is_held=False) == risk


async def test_compute_customer_risk_notify_band_is_pending():
    risk = guardian_service.compute_customer_risk("notify", is_held=False)
    assert risk == {"tier": "unusual", "phrase": None, "status": "pending"}


async def test_compute_customer_risk_step_up_band_is_pending():
    risk = guardian_service.compute_customer_risk("step_up", is_held=False)
    assert risk == {"tier": "potentially_dangerous", "phrase": None, "status": "pending"}


async def test_compute_customer_risk_hold_band_actually_held():
    risk = guardian_service.compute_customer_risk("hold", is_held=True)
    assert risk == {"tier": "held", "phrase": HELD_CUSTOMER_PHRASE, "status": "ready"}


async def test_compute_customer_risk_hold_band_shadow_mode_reconciliation():
    """Cazul subtil: banda calculată e "hold", dar shadow mode a suprimat
    aplicarea reală — clientul NU are voie să vadă "held" (nimic n-a fost
    reținut cu adevărat), cade pe "potentially_dangerous"."""
    risk = guardian_service.compute_customer_risk("hold", is_held=False)
    assert risk == {"tier": "potentially_dangerous", "phrase": None, "status": "pending"}


# --- generate_guardian_explanations (scrie în DB) ---------------------------


async def _seed_evaluation_and_transaction(*, band: str, score: int, risk: dict) -> ObjectId:
    db = get_database()
    tx_id = ObjectId()
    await db.transactions.insert_one(
        {
            "_id": tx_id,
            "status": "pending_review" if band == "hold" and risk["tier"] == "held" else "completed",
            "risk": risk,
            "created_at": datetime.now(timezone.utc),
        }
    )
    await db.fraud_evaluations.insert_one(
        {
            "transaction_id": tx_id,
            "user_id": "user-1",
            "status": "ok",
            "score": score,
            "fired_rules": [
                {"rule_id": "AMT-01", "family": "amount", "weight": 25, "contribution": 25.0, "excluded_from_score": False, "values": {"amount_minor": 100}}
            ],
            "decision_would_apply": band,
            "ruleset_version": "test-v1",
            "shadow_mode": False,
            "evaluated_at": datetime.now(timezone.utc),
            "error": None,
            "created_at": datetime.now(timezone.utc),
        }
    )
    return tx_id


async def test_success_path_writes_llm_output_and_updates_risk(monkeypatch):
    tx_id = await _seed_evaluation_and_transaction(
        band="notify", score=45, risk={"tier": "unusual", "phrase": None, "status": "pending"}
    )

    async def fake_complete_json(messages):
        return {"customer_phrase": "Frază generată de LLM.", "staff_explanation": "Explicație detaliată pentru personal."}

    monkeypatch.setattr("app.guardian.service.llm_client.complete_json", fake_complete_json)

    await guardian_service.generate_guardian_explanations(transaction_id=tx_id, user_id="user-1")

    db = get_database()
    evaluation = await db.fraud_evaluations.find_one({"transaction_id": tx_id})
    assert evaluation["guardian"]["status"] == "ready"
    assert evaluation["guardian"]["source"] == "llm"
    assert evaluation["guardian"]["customer_phrase"] == "Frază generată de LLM."
    assert evaluation["guardian"]["staff_explanation"] == "Explicație detaliată pentru personal."
    assert evaluation["guardian"]["customer_tier"] == "unusual"

    transaction = await db.transactions.find_one({"_id": tx_id})
    assert transaction["risk"]["phrase"] == "Frază generată de LLM."
    assert transaction["risk"]["status"] == "ready"


async def test_llm_failure_falls_back_to_template(monkeypatch):
    tx_id = await _seed_evaluation_and_transaction(
        band="step_up", score=65, risk={"tier": "potentially_dangerous", "phrase": None, "status": "pending"}
    )

    async def fake_complete_json(messages):
        return None

    monkeypatch.setattr("app.guardian.service.llm_client.complete_json", fake_complete_json)

    await guardian_service.generate_guardian_explanations(transaction_id=tx_id, user_id="user-1")

    db = get_database()
    evaluation = await db.fraud_evaluations.find_one({"transaction_id": tx_id})
    assert evaluation["guardian"]["status"] == "template_fallback"
    assert evaluation["guardian"]["source"] == "template"
    assert evaluation["guardian"]["customer_phrase"]  # nu e gol
    assert "AMT-01" in evaluation["guardian"]["staff_explanation"]  # șablonul numește regula

    transaction = await db.transactions.find_one({"_id": tx_id})
    assert transaction["risk"]["status"] == "template_fallback"


async def test_guardian_disabled_is_a_complete_noop(monkeypatch):
    tx_id = await _seed_evaluation_and_transaction(
        band="notify", score=45, risk={"tier": "unusual", "phrase": None, "status": "pending"}
    )
    monkeypatch.setattr("app.config.settings.guardian_enabled", False)

    called = False

    async def fake_complete_json(messages):
        nonlocal called
        called = True
        return {"customer_phrase": "x", "staff_explanation": "y"}

    monkeypatch.setattr("app.guardian.service.llm_client.complete_json", fake_complete_json)

    await guardian_service.generate_guardian_explanations(transaction_id=tx_id, user_id="user-1")

    assert called is False
    db = get_database()
    evaluation = await db.fraud_evaluations.find_one({"transaction_id": tx_id})
    assert "guardian" not in evaluation
    transaction = await db.transactions.find_one({"_id": tx_id})
    assert transaction["risk"]["status"] == "pending"  # neatins


async def test_hold_band_writes_guardian_but_never_touches_already_finalized_risk(monkeypatch):
    """Un hold REAL are deja risk.status="ready" (setat sincron, în
    create_transfer) — Guardian scrie DOAR guardian.* aici, transactions.risk
    rămâne EXACT cum era."""
    tx_id = await _seed_evaluation_and_transaction(
        band="hold", score=95, risk={"tier": "held", "phrase": HELD_CUSTOMER_PHRASE, "status": "ready"}
    )

    async def fake_complete_json(messages):
        return {"customer_phrase": "n-ar trebui folosită", "staff_explanation": "Explicație pentru personal, hold."}

    monkeypatch.setattr("app.guardian.service.llm_client.complete_json", fake_complete_json)

    await guardian_service.generate_guardian_explanations(transaction_id=tx_id, user_id="user-1")

    db = get_database()
    evaluation = await db.fraud_evaluations.find_one({"transaction_id": tx_id})
    assert evaluation["guardian"]["staff_explanation"] == "Explicație pentru personal, hold."

    transaction = await db.transactions.find_one({"_id": tx_id})
    assert transaction["risk"] == {"tier": "held", "phrase": HELD_CUSTOMER_PHRASE, "status": "ready"}


async def test_adversarial_llm_response_cannot_alter_other_fields(monkeypatch):
    """Chiar dacă LLM-ul (compromis sau halucinant) întoarce chei care arată
    ca o decizie, ele n-au NICIUN efect — output-ul e citit STRICT prin
    .get('customer_phrase')/.get('staff_explanation'), niciodată desfăcut
    într-un update Mongo."""
    tx_id = await _seed_evaluation_and_transaction(
        band="notify", score=45, risk={"tier": "unusual", "phrase": None, "status": "pending"}
    )

    async def adversarial_complete_json(messages):
        return {
            "customer_phrase": "Frază validă.",
            "staff_explanation": "Explicație validă.",
            "decision_would_apply": "pass",
            "score": 0,
            "status": "evaluation_error",
            "hold": {"resolution": "released"},
        }

    monkeypatch.setattr("app.guardian.service.llm_client.complete_json", adversarial_complete_json)

    db = get_database()
    evaluation_before = await db.fraud_evaluations.find_one({"transaction_id": tx_id})
    transaction_before = await db.transactions.find_one({"_id": tx_id})

    await guardian_service.generate_guardian_explanations(transaction_id=tx_id, user_id="user-1")

    evaluation_after = await db.fraud_evaluations.find_one({"transaction_id": tx_id})
    transaction_after = await db.transactions.find_one({"_id": tx_id})

    # Câmpurile deciziei rămân EXACT cele originale.
    assert evaluation_after["score"] == evaluation_before["score"] == 45
    assert evaluation_after["decision_would_apply"] == evaluation_before["decision_would_apply"] == "notify"
    assert evaluation_after["status"] == evaluation_before["status"] == "ok"
    assert transaction_after["status"] == transaction_before["status"]
    assert "hold" not in transaction_after

    # Singurele câmpuri noi/schimbate sunt cele explicit permise.
    assert evaluation_after["guardian"]["customer_phrase"] == "Frază validă."
    assert transaction_after["risk"]["phrase"] == "Frază validă."
