"""Indexare idempotentă pentru fraud/ — apelată din app/main.py::lifespan,
la fel ca în celelalte servicii (vezi auth-service/app/webauthn_service.py
::ensure_webauthn_indexes, accounts-service/app/service.py
::backfill_missing_account_types). NU există migrări în acest proiect
(Mongo, nu SQL) — indexarea idempotentă e mecanismul de evoluție a schemei.
"""

from app.database import get_database


async def ensure_fraud_indexes() -> None:
    db = get_database()
    await db.fraud_profiles.create_index("user_id", unique=True)
    await db.fraud_evaluations.create_index("transaction_id", unique=True)
    await db.fraud_evaluations.create_index([("user_id", 1), ("evaluated_at", -1)])
    await db.fraud_evaluations.create_index([("evaluated_at", -1), ("score", 1)])
    await db.fraud_evaluations.create_index("status")
    # Pentru lista de personal (routers/staff.py) — "arată-mi cele
    # nerevizuite mai întâi" filtrează pe existența review.reviewed_at.
    await db.fraud_evaluations.create_index("review.reviewed_at")

    # Nu sunt colecții NOI de fraud, dar interogările "fereastră live" din
    # context.py (VEL/BEN/STR/BEH) rulează pe db.transactions la FIECARE
    # transfer — fără aceste 2 indexuri ar deveni scanări complete de
    # colecție exact pe calea sincronă de plată, contrazicând bugetul de
    # <50ms p99 din plan.
    await db.transactions.create_index([("from_account_id", 1), ("created_at", -1)])
    await db.transactions.create_index([("to_account_id", 1), ("created_at", -1)])
