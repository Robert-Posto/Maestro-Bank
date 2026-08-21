"""Singurul modul (alături de audit.py) care atinge tx_db.fraud_evaluations
— de data asta din perspectiva PERSONALULUI care revizuiește/adnotează
evaluări deja scrise. Nu scrie NICIODATĂ score/fired_rules/decision_would_apply
— acelea rămân decizia automată originală, imuabilă (vezi fraud/models.py
::EvaluationReview). Vezi app/routers/staff.py pentru rutele HTTP (protejate
cu RequireStaff — app/security.py) care apelează acest modul.
"""

from datetime import datetime

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status

from app.database import get_database

_MAX_LIMIT = 100


async def list_evaluations(
    *,
    decision_band: str | None,
    reviewed: bool | None,
    since: datetime | None,
    until: datetime | None,
    limit: int,
    skip: int,
) -> list[dict]:
    db = get_database()
    query: dict = {}
    if decision_band is not None:
        query["decision_would_apply"] = decision_band
    if reviewed is not None:
        query["review"] = {"$exists": reviewed}
    if since is not None or until is not None:
        query["evaluated_at"] = {
            **({"$gte": since} if since is not None else {}),
            **({"$lte": until} if until is not None else {}),
        }

    cursor = db.fraud_evaluations.find(query).sort("evaluated_at", -1).skip(skip).limit(min(limit, _MAX_LIMIT))
    return await cursor.to_list(length=min(limit, _MAX_LIMIT))


def _to_object_id(evaluation_id: str) -> ObjectId:
    try:
        return ObjectId(evaluation_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evaluare inexistentă.") from exc


async def get_evaluation(evaluation_id: str) -> dict:
    db = get_database()
    evaluation = await db.fraud_evaluations.find_one({"_id": _to_object_id(evaluation_id)})
    if evaluation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evaluare inexistentă.")
    return evaluation


async def review_evaluation(
    *, evaluation_id: str, staff_user_id: str, outcome: str, note: str, reviewed_at: datetime
) -> dict:
    """O evaluare poate fi revizuită O SINGURĂ dată — filtrul
    `{"review": {"$exists": False}}` face asta atomic (nu read-then-write),
    ca o rescriere accidentală/concurentă a unei revizuiri deja făcute să
    nu fie posibilă. O a doua opinie despre aceeași evaluare e o decizie
    separată, care ar avea nevoie de un mecanism propriu — nu o suprascriere
    tăcută a primei."""
    db = get_database()
    object_id = _to_object_id(evaluation_id)

    review_doc = {
        "reviewed_by": staff_user_id,
        "reviewed_at": reviewed_at,
        "outcome": outcome,
        "note": note,
    }
    result = await db.fraud_evaluations.update_one(
        {"_id": object_id, "review": {"$exists": False}},
        {"$set": {"review": review_doc}},
    )
    if result.matched_count == 0:
        existing = await db.fraud_evaluations.find_one({"_id": object_id})
        if existing is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evaluare inexistentă.")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Această evaluare a fost deja revizuită.")

    return await db.fraud_evaluations.find_one({"_id": object_id})
