"""Teste pentru app/fraud/reporting.py::build_shadow_report — real Mongo
(agregare la citire, vezi docstring-ul modulului), fără API HTTP.
"""

from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId

from app.database import get_database
from app.fraud.reporting import build_shadow_report

pytestmark = pytest.mark.asyncio

USER_ID = str(ObjectId())


def _evaluation(**overrides) -> dict:
    base = dict(
        transaction_id=ObjectId(),
        user_id=USER_ID,
        status="ok",
        score=42,
        fired_rules=[],
        decision_would_apply="pass",
        ruleset_version="test",
        shadow_mode=True,
        evaluated_at=datetime.now(timezone.utc),
        error=None,
        created_at=datetime.now(timezone.utc),
    )
    base.update(overrides)
    return base


async def test_score_histogram_buckets_by_ten():
    db = get_database()
    await db.fraud_evaluations.insert_many([_evaluation(score=12), _evaluation(score=15), _evaluation(score=87)])

    report = await build_shadow_report(None, None)

    assert report["score_histogram"]["10-19"] == 2
    assert report["score_histogram"]["80-89"] == 1


async def test_null_score_evaluations_excluded_from_histogram_not_crash():
    """Regresie — BEN-04 (vezi app/blocklist.py) scrie evaluări
    status="ok" cu score=None (refuz direct, fără scoring). Pipeline-ul
    Mongo de agregare a scorului propagă null prin $divide/$floor, ceea ce
    provoca un TypeError la int(None) înainte de fix — vezi
    app/fraud/reporting.py."""
    db = get_database()
    await db.fraud_evaluations.insert_many(
        [
            _evaluation(score=50),
            _evaluation(score=None, decision_would_apply="reject", fired_rules=[]),
        ]
    )

    report = await build_shadow_report(None, None)

    assert report["score_histogram"] == {"50-59": 1}
    assert report["by_status"] == {"ok": 2}


async def test_decision_band_and_rule_fire_counts():
    db = get_database()
    await db.fraud_evaluations.insert_many(
        [
            _evaluation(score=90, decision_would_apply="hold", fired_rules=[{"rule_id": "VEL-04", "excluded_from_score": False}]),
            _evaluation(score=90, decision_would_apply="hold", fired_rules=[{"rule_id": "VEL-04", "excluded_from_score": False}]),
            _evaluation(score=10, decision_would_apply="pass"),
        ]
    )

    report = await build_shadow_report(None, None)

    assert report["by_decision_band"]["hold"] == 2
    assert report["rule_fire_counts"]["VEL-04"] == {"fire_count": 2, "excluded_from_score": False}


async def test_window_filters_by_evaluated_at():
    db = get_database()
    old = _evaluation(score=99, evaluated_at=datetime.now(timezone.utc) - timedelta(days=30))
    recent = _evaluation(score=1)
    await db.fraud_evaluations.insert_many([old, recent])

    report = await build_shadow_report(datetime.now(timezone.utc) - timedelta(days=1), None)

    assert report["total_evaluations"] == 1
