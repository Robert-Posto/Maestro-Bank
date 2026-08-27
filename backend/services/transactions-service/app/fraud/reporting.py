"""Raportare shadow-mode — vezi planul: agregare Mongo la cerere, FĂRĂ
colecție nouă și FĂRĂ job programat. E o unealtă folosită manual, de câteva
ori, în timpul calibrării — nu un hot path — deci pre-agregarea într-o
colecție separată ar fi cost prematur (scriere suplimentară la fiecare
transfer, pentru un citit rar).
"""

from datetime import datetime, timedelta, timezone

from app.database import get_database

_DEFAULT_WINDOW_DAYS = 7
_SCORE_BUCKET_SIZE = 10


async def build_shadow_report(since: datetime | None, until: datetime | None) -> dict:
    db = get_database()
    now = until or datetime.now(timezone.utc)
    window_start = since or (now - timedelta(days=_DEFAULT_WINDOW_DAYS))
    match_stage = {"evaluated_at": {"$gte": window_start, "$lte": now}}
    ok_match_stage = {**match_stage, "status": "ok"}

    total = await db.fraud_evaluations.count_documents(match_stage)

    status_rows = await db.fraud_evaluations.aggregate(
        [{"$match": match_stage}, {"$group": {"_id": "$status", "count": {"$sum": 1}}}]
    ).to_list(length=10)

    band_rows = await db.fraud_evaluations.aggregate(
        [{"$match": ok_match_stage}, {"$group": {"_id": "$decision_would_apply", "count": {"$sum": 1}}}]
    ).to_list(length=10)

    score_rows = await db.fraud_evaluations.aggregate(
        [
            {"$match": ok_match_stage},
            {
                "$project": {
                    "bucket": {"$multiply": [{"$floor": {"$divide": ["$score", _SCORE_BUCKET_SIZE]}}, _SCORE_BUCKET_SIZE]}
                }
            },
            {"$group": {"_id": "$bucket", "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}},
        ]
    ).to_list(length=20)

    rule_rows = await db.fraud_evaluations.aggregate(
        [
            {"$match": ok_match_stage},
            {"$unwind": "$fired_rules"},
            {
                "$group": {
                    "_id": "$fired_rules.rule_id",
                    "fire_count": {"$sum": 1},
                    "excluded_from_score": {"$first": "$fired_rules.excluded_from_score"},
                }
            },
            {"$sort": {"fire_count": -1}},
        ]
    ).to_list(length=50)

    return {
        "window": {"since": window_start.isoformat(), "until": now.isoformat()},
        "total_evaluations": total,
        "by_status": {row["_id"]: row["count"] for row in status_rows},
        "by_decision_band": {row["_id"]: row["count"] for row in band_rows if row["_id"] is not None},
        # score=None (BEN-04 — refuz direct, fără scoring, vezi
        # app/blocklist.py) produce bucket=None din pipeline-ul Mongo de mai
        # sus ($divide pe null propagă null) — exclus aici, la fel ca
        # by_decision_band mai sus, NU un scor real de agregat într-o bandă.
        "score_histogram": {
            f"{int(row['_id'])}-{int(row['_id']) + _SCORE_BUCKET_SIZE - 1}": row["count"]
            for row in score_rows
            if row["_id"] is not None
        },
        "rule_fire_counts": {
            row["_id"]: {"fire_count": row["fire_count"], "excluded_from_score": row["excluded_from_score"]}
            for row in rule_rows
        },
    }
