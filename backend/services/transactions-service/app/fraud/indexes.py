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
    # BEN-01/VEL-03/VEL-05 filtrează toate pe (from_account_id, to_iban) —
    # fără index dedicat, "seen_before" (BEN-01) plătea deja costul unei
    # scanări neacoperite o dată per transfer; VEL-03 multiplică exact
    # acel cost de N ori (N = beneficiari noi-candidați din fereastră).
    await db.transactions.create_index([("from_account_id", 1), ("to_iban", 1), ("created_at", -1)])
