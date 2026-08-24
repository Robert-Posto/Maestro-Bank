"""Singurul modul care atinge tx_db.fraud_cohort_baseline — baseline
agregat, non-personal, folosit DOAR la cold start (vezi rules_amount.py,
rules_temporal.py).

Un singur cohort GLOBAL în Faza 1 — fără segmentare pe vechime/tip cont
(`InternalAccountView` din accounts-service nu expune `created_at` de cont
încă; adăugarea acelui câmp e un gap mic, dar în afara scopului Fazei 1,
documentat pentru Faza 2).
"""

from datetime import datetime, timedelta

from app.database import get_database
from app.fraud.models import CohortBaseline
from app.fraud.ruleset_config import RulesetConfig
from app.fraud.stats import percentile

_COHORT_DOC_ID = "global"
_AGGREGATION_WINDOW_DAYS = 30


async def get_cohort_baseline(evaluated_at: datetime, ruleset: RulesetConfig) -> CohortBaseline:
    db = get_database()
    doc = await db.fraud_cohort_baseline.find_one({"_id": _COHORT_DOC_ID})
    ttl = timedelta(hours=ruleset.cohort_baseline_ttl_hours)
    if doc is not None and (evaluated_at - doc["computed_at"]) <= ttl:
        return _to_baseline(doc)

    baseline_doc = await _recompute(evaluated_at, ruleset)
    return _to_baseline(baseline_doc)


def _to_baseline(doc: dict) -> CohortBaseline:
    return CohortBaseline(
        sample_size=doc.get("sample_size", 0),
        p95_amount_minor=doc.get("p95_amount_minor", 0),
        median_amount_minor=doc.get("median_amount_minor", 0),
        average_amount_minor=doc.get("average_amount_minor", 0),
        median_amount_minor_by_category=doc.get("median_amount_minor_by_category", {}),
        hour_p5=doc.get("hour_p5", 0),
        hour_p95=doc.get("hour_p95", 23),
    )


async def _recompute(evaluated_at: datetime, ruleset: RulesetConfig) -> dict:
    db = get_database()
    cutoff = evaluated_at - timedelta(days=_AGGREGATION_WINDOW_DAYS)
    cursor = (
        db.transactions.find(
            {"status": "completed", "created_at": {"$gte": cutoff, "$lte": evaluated_at}},
            {"amount_minor": 1, "category": 1, "created_at": 1},
        )
        .sort("created_at", -1)
        .limit(ruleset.cohort_sample_size)
    )
    rows = await cursor.to_list(length=ruleset.cohort_sample_size)

    baseline_doc: dict = {"_id": _COHORT_DOC_ID, "computed_at": evaluated_at, "sample_size": len(rows)}
    if rows:
        amounts = [r["amount_minor"] for r in rows]
        by_category: dict[str, list[int]] = {}
        for row in rows:
            by_category.setdefault(row.get("category", "other"), []).append(row["amount_minor"])
        # created_at citit din Mongo e naiv (fără tzinfo) — vezi timeutil.py.
        # .hour direct pe un naiv-UTC e deja ora UTC corectă, fără conversie.
        hours = [row["created_at"].hour for row in rows]

        baseline_doc.update(
            p95_amount_minor=round(percentile(amounts, 95)),
            median_amount_minor=round(percentile(amounts, 50)),
            average_amount_minor=round(sum(amounts) / len(amounts)),
            median_amount_minor_by_category={cat: round(percentile(vals, 50)) for cat, vals in by_category.items()},
            hour_p5=round(percentile(hours, 5)),
            hour_p95=round(percentile(hours, 95)),
        )
    else:
        baseline_doc.update(
            p95_amount_minor=0,
            median_amount_minor=0,
            average_amount_minor=0,
            median_amount_minor_by_category={},
            hour_p5=0,
            hour_p95=23,
        )

    await db.fraud_cohort_baseline.replace_one({"_id": _COHORT_DOC_ID}, baseline_doc, upsert=True)
    return baseline_doc
