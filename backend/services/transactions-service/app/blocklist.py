"""Lista de beneficiari BLOCAȚI (tx_db.beneficiary_blocklist) — BEN-04.

Singura regulă din catalog care NU trece prin sistemul de scor 0-100 (vezi
app/fraud/) — un beneficiar de pe listă înseamnă REFUZ DIRECT, înainte de
orice scoring, la fel ca "hard rule fired" din spec-ul sursă
(guardian-claude-code-prompt.md). Vezi app/service.py::create_transfer
pentru punctul exact unde e verificată lista, ÎNAINTE de inserarea
tranzacției.

Scriere DOAR de către personal (RequireStaff) — fie automat, când o
evaluare e marcată "confirmed_fraud" (vezi fraud/staff.py::review_evaluation),
fie manual, din pagina de admin. NICIODATĂ dintr-un raport de fraudă al
unui client — un raport eronat/rău-intenționat de la UN client n-ar trebui
să blocheze bancar un beneficiar pentru TOȚI clienții."""

from datetime import datetime, timezone
from typing import Literal

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status

from app.database import get_database
from app.i18n import translate


async def ensure_blocklist_indexes() -> None:
    db = get_database()
    await db.beneficiary_blocklist.create_index("iban", unique=True)


async def is_blocked(iban: str) -> dict | None:
    """Apelat DOAR din create_transfer, ÎNAINTE de scoring — vezi
    modulul docstring. None = nu e blocat."""
    db = get_database()
    return await db.beneficiary_blocklist.find_one({"iban": iban})


async def add_to_blocklist(
    *, iban: str, added_by: str, reason: str, source: Literal["confirmed_fraud_review", "manual"],
    evaluation_id: ObjectId | None = None,
) -> dict:
    """Idempotent pe `iban` (index unic) — o re-confirmare sau mai multe
    evaluări către ACELAȘI IBAN nu creează duplicate, doar actualizează
    motivul/sursa cu cea mai recentă."""
    db = get_database()
    now = datetime.now(timezone.utc)
    await db.beneficiary_blocklist.update_one(
        {"iban": iban},
        {
            "$set": {"added_by": added_by, "reason": reason, "source": source, "evaluation_id": evaluation_id},
            "$setOnInsert": {"iban": iban, "created_at": now},
        },
        upsert=True,
    )
    return await db.beneficiary_blocklist.find_one({"iban": iban})


async def list_blocklist(limit: int = 100, skip: int = 0) -> list[dict]:
    db = get_database()
    return await db.beneficiary_blocklist.find().sort("created_at", -1).skip(skip).limit(min(limit, 100)).to_list(length=100)


async def remove_from_blocklist(entry_id: str) -> None:
    db = get_database()
    try:
        object_id = ObjectId(entry_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=translate("invalidId")) from exc

    result = await db.beneficiary_blocklist.delete_one({"_id": object_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=translate("entryNotFound"))
