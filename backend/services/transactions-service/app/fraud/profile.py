"""Singurul modul care atinge tx_db.fraud_profiles — profilul materializat,
incremental, per user.

Materializat + actualizat incremental, NU recalculat live: fără Redis în
acest stack, o agregare completă peste istoricul de 90 zile al userului la
FIECARE transfer ar deveni tot mai costisitoare exact pe măsură ce se
acumulează datele de calibrare pe care shadow mode există să le colecteze —
direcția greșită. `history_samples` e un buffer circular (cap 300, via
`$push`/`$slice`), nu un algoritm de percentile în flux — nu există
numpy/scipy în acest proiect.
"""

from datetime import datetime

from app.database import get_database
from app.fraud.models import HistorySample, UserProfileSnapshot

_HISTORY_SAMPLE_CAP = 300


async def get_profile(user_id: str) -> UserProfileSnapshot:
    db = get_database()
    doc = await db.fraud_profiles.find_one({"user_id": user_id})
    if doc is None:
        return UserProfileSnapshot.empty()
    return UserProfileSnapshot(
        transaction_count=doc.get("transaction_count", 0),
        first_transaction_at=doc.get("first_transaction_at"),
        last_transaction_at=doc.get("last_transaction_at"),
        history_samples=tuple(HistorySample(**sample) for sample in doc.get("history_samples", [])),
        category_counts=doc.get("category_counts", {}),
        beneficiary_countries=tuple(doc.get("beneficiary_countries", [])),
    )


async def update_profile_after_transfer(
    *, user_id: str, amount_minor: int, category: str, to_iban: str, created_at: datetime
) -> None:
    """Best-effort — apelat DOAR pentru transferuri "completed" (vezi
    fraud/service.py::record_completed_transfer_for_profile), NICIODATĂ
    pentru "pending"/"failed". Un profil stale/lipsă degradează spre cold
    start la următoarea evaluare — sigur, auto-corectiv — de-aia eșecul aici
    NU e tratat cu aceeași strictețe ca audit.py."""
    db = get_database()
    sample = {
        "amount_minor": amount_minor,
        "category": category,
        "hour_utc": created_at.hour,
        "created_at": created_at,
    }
    await db.fraud_profiles.update_one(
        {"user_id": user_id},
        {
            "$inc": {"transaction_count": 1, f"category_counts.{category}": 1},
            "$set": {"last_transaction_at": created_at, "updated_at": created_at},
            "$setOnInsert": {"first_transaction_at": created_at, "created_at": created_at, "user_id": user_id},
            "$push": {"history_samples": {"$each": [sample], "$slice": -_HISTORY_SAMPLE_CAP}},
            "$addToSet": {"beneficiary_countries": to_iban[:2]},
        },
        upsert=True,
    )
