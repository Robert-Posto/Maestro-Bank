"""Singurul modul care adună fapte din DB/HTTP pentru o evaluare — vezi
fraud/service.py pentru cum e apelat. Tot ce produce ajunge împachetat în
DTO-uri imuabile (fraud/models.py) înainte să treacă la scoring.py, care
rămâne pur.

Interogările "fereastră live" (VEL/BEN/STR/BEH) rulează DUPĂ ce tranzacția
curentă a fost deja inserată (vezi hook-ul 1 din app/service.py::create_transfer)
— asta le include automat pe ea în numărători/sume, fără cod special de
"current + istoric". SINGURA excepție e `seen_before` (BEN-01), care exclude
explicit `transaction_id` — întrebarea acolo e "a mai plătit userul acest
beneficiar ÎNAINTE de acum", nu "a mai plătit, numărând și acum"."""

import logging
from datetime import datetime, timedelta

import httpx
from bson import ObjectId

from app.config import settings
from app.database import get_database
from app.fraud import cohort
from app.fraud import profile as profile_module
from app.fraud.models import (
    BeneficiaryWindow,
    CohortBaseline,
    DeviceFacts,
    RuleContext,
    TransactionSnapshot,
    WindowFacts,
)
from app.fraud.ruleset_config import RulesetConfig

logger = logging.getLogger("transactions-service")

_DEV03_TIMEOUT_SECONDS = 0.4
_NOT_FAILED = {"$ne": "failed"}


async def build_rule_context(
    *,
    transaction_id: ObjectId,
    transaction: dict,
    source_balance_minor: int,
    user_id: str,
    evaluated_at: datetime,
    ruleset: RulesetConfig,
) -> RuleContext:
    account_id = transaction["from_account_id"]
    to_iban = transaction["to_iban"]
    amount_minor = transaction["amount_minor"]

    user_profile = await profile_module.get_profile(user_id)

    cohort_baseline = CohortBaseline()
    if user_profile.transaction_count < ruleset.cold_start_min_transactions:
        # Doar cold-start plătește costul agregării/cache-ului de cohortă —
        # utilizatorii stabiliți nu au nevoie de ea, deloc, pe calea rapidă.
        cohort_baseline = await cohort.get_cohort_baseline(evaluated_at, ruleset)

    window = await _build_window_facts(
        transaction_id=transaction_id,
        account_id=account_id,
        to_iban=to_iban,
        amount_minor=amount_minor,
        evaluated_at=evaluated_at,
        ruleset=ruleset,
    )
    device = await _build_device_facts(user_id=user_id)

    return RuleContext(
        transaction=TransactionSnapshot(
            amount_minor=amount_minor,
            category=transaction["category"],
            to_iban=to_iban,
            from_account_id=account_id,
            to_account_id=transaction["to_account_id"],
        ),
        source_balance_minor=source_balance_minor,
        profile=user_profile,
        window=window,
        cohort=cohort_baseline,
        device=device,
        evaluated_at=evaluated_at,
    )


async def _build_window_facts(
    *,
    transaction_id: ObjectId,
    account_id: str,
    to_iban: str,
    amount_minor: int,
    evaluated_at: datetime,
    ruleset: RulesetConfig,
) -> WindowFacts:
    db = get_database()

    count_10min = await db.transactions.count_documents(
        {
            "from_account_id": account_id,
            "status": _NOT_FAILED,
            "created_at": {"$gte": evaluated_at - timedelta(minutes=10)},
        }
    )

    amount_1h_rows = await db.transactions.aggregate(
        [
            {
                "$match": {
                    "from_account_id": account_id,
                    "status": _NOT_FAILED,
                    "created_at": {"$gte": evaluated_at - timedelta(hours=1)},
                }
            },
            {"$group": {"_id": None, "total": {"$sum": "$amount_minor"}}},
        ]
    ).to_list(length=1)
    amount_1h = amount_1h_rows[0]["total"] if amount_1h_rows else 0

    seen_before_count = await db.transactions.count_documents(
        {"from_account_id": account_id, "to_iban": to_iban, "_id": {"$ne": transaction_id}}, limit=1
    )

    beneficiary_rows = await (
        db.transactions.find(
            {
                "from_account_id": account_id,
                "to_iban": to_iban,
                "status": _NOT_FAILED,
                "created_at": {"$gte": evaluated_at - timedelta(minutes=30)},
            },
            {"amount_minor": 1, "created_at": 1},
        )
        .sort("created_at", 1)
        .to_list(length=50)
    )

    distinct_senders = await db.transactions.distinct(
        "from_account_id",
        {"to_iban": to_iban, "status": _NOT_FAILED, "created_at": {"$gte": evaluated_at - timedelta(hours=24)}},
    )

    distinct_beneficiaries = await db.transactions.distinct(
        "to_iban",
        {
            "from_account_id": account_id,
            "amount_minor": amount_minor,
            "status": _NOT_FAILED,
            "created_at": {"$gte": evaluated_at - timedelta(minutes=ruleset.str02_window_minutes)},
        },
    )

    incoming_cutoff = evaluated_at - timedelta(hours=ruleset.beh03_window_hours)
    incoming_rows = await (
        db.transactions.find(
            {"to_account_id": account_id, "status": "completed", "created_at": {"$gte": incoming_cutoff, "$lt": evaluated_at}},
            {"amount_minor": 1},
        )
        .sort("created_at", -1)
        .limit(1)
        .to_list(length=1)
    )
    recent_incoming = incoming_rows[0]["amount_minor"] if incoming_rows else None

    return WindowFacts(
        count_last_10min=count_10min,
        amount_last_1h_minor=amount_1h,
        beneficiary=BeneficiaryWindow(
            seen_before=seen_before_count > 0,
            recent_amounts_same_beneficiary=tuple(r["amount_minor"] for r in beneficiary_rows),
            distinct_senders_last_24h=len(distinct_senders),
        ),
        identical_amount_distinct_beneficiaries_60min=len(distinct_beneficiaries),
        recent_incoming_credit_minor=recent_incoming,
    )


async def _build_device_facts(*, user_id: str) -> DeviceFacts:
    """DEV-03 — singurul network hop dintr-un motor altfel complet
    în-proces. Timeout scurt (deliberat mai mic decât cel de 5s folosit în
    rest de service.py) + fail-open: orice eroare -> regula pur și simplu
    nu se declanșează, niciodată confundată tacit cu "nu există înrolare"."""
    try:
        async with httpx.AsyncClient(timeout=_DEV03_TIMEOUT_SECONDS) as client:
            response = await client.get(
                f"{settings.auth_service_url}/internal/webauthn/credentials/by-user/{user_id}/latest"
            )
        if response.status_code != 200:
            raise httpx.HTTPError(f"status neașteptat {response.status_code}")
        body = response.json()
        latest_raw = body.get("latest_created_at")
        latest = datetime.fromisoformat(latest_raw) if latest_raw else None
        return DeviceFacts(latest_passkey_created_at=latest, data_available=True)
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("fraud: DEV-03 indisponibil (auth-service, user_id=%s): %s", user_id, exc)
        return DeviceFacts(latest_passkey_created_at=None, data_available=False)
