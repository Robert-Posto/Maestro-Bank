"""Singurul modul care atinge tx_db.fraud_evaluations — jurnalul de audit
cerut de GDPR Art. 22 (dreptul la explicație / contestare a deciziilor
automate — vezi planul). O evaluare eșuată tot trebuie să lase o urmă
(`status="evaluation_error"`) — exact momentul în care ceva a mers prost e
cel mai relevant de auditat, nu unul de ignorat.
"""

import logging
from datetime import datetime, timezone

from bson import ObjectId

from app.config import settings
from app.database import get_database
from app.fraud.models import ScoreResult

logger = logging.getLogger("transactions-service")

_WRITE_RETRIES = 1


async def record_evaluation(*, transaction_id: ObjectId, user_id: str, result: ScoreResult, evaluated_at: datetime) -> None:
    doc = {
        "transaction_id": transaction_id,
        "user_id": user_id,
        "status": "ok",
        "score": result.score,
        "fired_rules": [rule.model_dump() for rule in result.fired_rules],
        "decision_would_apply": result.decision_would_apply,
        "ruleset_version": result.ruleset_version,
        # Reflectă VALOAREA REALĂ a comutatorului la momentul evaluării, nu
        # mai e hardcodat True — Faza "PENDING hold" a făcut acest flag
        # real, configurabil. O evaluare shadow_mode=False cu
        # decision_would_apply="hold" e cea care a CHIAR reținut bani.
        "shadow_mode": settings.fraud_shadow_mode,
        "evaluated_at": evaluated_at,
        "error": None,
    }
    await _write_with_fallback(doc)


async def record_blocklist_rejection(*, transaction_id: ObjectId, user_id: str, evaluated_at: datetime) -> None:
    """BEN-04 — refuz direct, ÎNAINTE de scoring (vezi
    app/blocklist.py/app/service.py::create_transfer). NU e o evaluare
    "ok" normală (n-a fost scoring deloc) — `decision_would_apply="reject"`
    e o bandă SEPARATĂ de pass/notify/step_up/hold, ca dreptul la
    explicație GDPR să acopere și acest caz."""
    doc = {
        "transaction_id": transaction_id,
        "user_id": user_id,
        "status": "ok",
        "score": None,
        "fired_rules": [],
        "decision_would_apply": "reject",
        "ruleset_version": "N/A — BEN-04, refuz direct fără scoring",
        "shadow_mode": settings.fraud_shadow_mode,
        "evaluated_at": evaluated_at,
        "error": None,
    }
    await _write_with_fallback(doc)


async def record_evaluation_error(
    *, transaction_id: ObjectId, user_id: str, ruleset_version: str, evaluated_at: datetime, error: Exception
) -> None:
    doc = {
        "transaction_id": transaction_id,
        "user_id": user_id,
        "status": "evaluation_error",
        "score": None,
        "fired_rules": [],
        "decision_would_apply": None,
        "ruleset_version": ruleset_version,
        "shadow_mode": settings.fraud_shadow_mode,
        "evaluated_at": evaluated_at,
        "error": str(error)[:500],
    }
    await _write_with_fallback(doc)


async def _write_with_fallback(doc: dict) -> None:
    db = get_database()
    # created_at = ora de perete la SCRIERE — strict operațional (detectare
    # întârzieri/reîncercări), scoring-ul nu-l citește niciodată. E singurul
    # loc din fraud/ unde un citire directă a ceasului e ok — nu participă
    # la nicio comparație de determinism.
    record = {**doc, "created_at": datetime.now(timezone.utc)}
    for attempt in range(_WRITE_RETRIES + 1):
        try:
            await db.fraud_evaluations.insert_one(dict(record))
            return
        except Exception as exc:
            if attempt < _WRITE_RETRIES:
                continue
            # Nicio scriere reușită — înregistrarea NU are voie să dispară
            # fără urmă (cerință de audit GDPR), deci ajunge integral în
            # log, recuperabilă manual de un proces ops/compliance, chiar
            # fără un outbox/WAL (infrastructură explicit în afara Fazei 1).
            logger.error("fraud: scriere audit EȘUATĂ definitiv — %s | record=%s", exc, record)
