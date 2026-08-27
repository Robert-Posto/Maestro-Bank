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
    CredentialEvent,
    DeviceFacts,
    LoginEvent,
    RuleContext,
    SecurityFacts,
    TransactionSnapshot,
    WindowFacts,
)
from app.fraud.ruleset_config import RulesetConfig

logger = logging.getLogger("transactions-service")

_DEV03_TIMEOUT_SECONDS = 0.4
_SECURITY_FACTS_TIMEOUT_SECONDS = 0.6  # un singur apel, dar întoarce mai multe date decât DEV-03 — puțin mai generos
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
    security = await _build_security_facts(user_id=user_id)

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
        security=security,
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

    new_beneficiaries_60min = await _count_new_beneficiaries_last_60min(
        db, account_id=account_id, evaluated_at=evaluated_at, ruleset=ruleset
    )
    near_threshold_24h = await _count_near_threshold_last_24h(
        db, account_id=account_id, evaluated_at=evaluated_at, ruleset=ruleset
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
        new_beneficiaries_last_60min=new_beneficiaries_60min,
        near_threshold_count_last_24h=near_threshold_24h,
    )


_VEL03_WINDOW_ROWS_CAP = 500  # gardă — VEL-01 (>5/10min) s-ar fi declanșat deja cu mult înainte de acest plafon


def _first_seen_per_iban(rows: list[dict]) -> dict[str, datetime]:
    """Pură — prima apariție a fiecărui to_iban distinct, presupunând
    `rows` deja sortate crescător după created_at."""
    first_seen: dict[str, datetime] = {}
    for row in rows:
        first_seen.setdefault(row["to_iban"], row["created_at"])
    return first_seen


async def _count_new_beneficiaries_last_60min(
    db, *, account_id: str, evaluated_at: datetime, ruleset: RulesetConfig
) -> int:
    """VEL-03 — reia forma EXACTĂ a lui seen_before_count de mai sus
    (BEN-01), aplicată o dată per beneficiar DISTINCT din fereastra de 60
    min, nu doar pentru beneficiarul tranzacției curente. NU e un
    $lookup — vezi planul fazei pentru motiv (context.py face doar
    agregări cu un singur stagiu azi; N-ul practic e mic, tiparul vizat e
    diversificarea de beneficiari, nu volumul brut — ăla îl prinde deja
    VEL-01)."""
    window_start = evaluated_at - timedelta(minutes=ruleset.vel03_window_minutes)
    rows = await (
        db.transactions.find(
            {"from_account_id": account_id, "status": _NOT_FAILED, "created_at": {"$gte": window_start}},
            {"to_iban": 1, "created_at": 1},
        )
        .sort("created_at", 1)
        .to_list(length=_VEL03_WINDOW_ROWS_CAP)
    )
    first_seen = _first_seen_per_iban(rows)

    new_count = 0
    for iban, first_seen_at in first_seen.items():
        # NU filtrăm status aici — reutilizăm semantica EXACTĂ a lui
        # BEN-01 ("a mai plătit userul acest beneficiar VREODATĂ înainte").
        # $lt first_seen_at exclude implicit tranzacțiile din fereastra
        # curentă (niciuna nu poate avea created_at < propria ei primă
        # apariție), deci nu mai e nevoie de o excludere explicită pe _id.
        seen_before = await db.transactions.count_documents(
            {"from_account_id": account_id, "to_iban": iban, "created_at": {"$lt": first_seen_at}}, limit=1
        )
        if seen_before == 0:
            new_count += 1
    return new_count


async def _count_near_threshold_last_24h(
    db, *, account_id: str, evaluated_at: datetime, ruleset: RulesetConfig
) -> int:
    """STR-01 — tranzacții proprii, ultimele 24h, sumă în banda
    [90%, 99%] a unui prag de "raportare" configurabil (implicit 50.000
    RON — decizie de PRODUS pentru acest demo, NU un prag legal real, vezi
    ruleset_config.py). Ambele capete ale benzii sunt INCLUSIVE — citire
    literală a "90-99%", ca AMT-04, nu strict ca AMT-03 (niciun precedent
    unic în acest fișier pentru un interval închis ca ăsta)."""
    lower_bound = round(ruleset.str01_reporting_threshold_minor * ruleset.str01_lower_ratio)
    upper_bound = round(ruleset.str01_reporting_threshold_minor * ruleset.str01_upper_ratio)
    return await db.transactions.count_documents(
        {
            "from_account_id": account_id,
            "status": _NOT_FAILED,
            "amount_minor": {"$gte": lower_bound, "$lte": upper_bound},
            "created_at": {"$gte": evaluated_at - timedelta(hours=ruleset.str01_window_hours)},
        }
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


async def _build_security_facts(*, user_id: str) -> SecurityFacts:
    """VEL-04, DEV-01/02/04/05/06 — AL DOILEA (și ultimul) network hop din
    acest motor, separat de DEV-03 (apel diferit, mai vechi) — UN SINGUR
    apel către auth-service adună istoricul de login + schimbări de
    credențiale, ca să nu multiplicăm hop-uri HTTP pe calea de evaluare
    fraud (vezi planul fazei). Timeout scurt + fail-open, exact ca DEV-03:
    orice eroare -> NICIUNA din cele 6 reguli care depind de asta nu se
    declanșează, niciodată confundată tacit cu "nu există istoric"."""
    try:
        async with httpx.AsyncClient(timeout=_SECURITY_FACTS_TIMEOUT_SECONDS) as client:
            response = await client.get(f"{settings.auth_service_url}/internal/security-facts/{user_id}")
        if response.status_code != 200:
            raise httpx.HTTPError(f"status neașteptat {response.status_code}")
        body = response.json()

        recent_logins = tuple(
            LoginEvent(
                success=item["success"],
                device_signature=item.get("device_signature"),
                country=item.get("country"),
                lat=item.get("lat"),
                lon=item.get("lon"),
                created_at=datetime.fromisoformat(item["created_at"]),
            )
            for item in body.get("recent_logins", [])
        )
        password_changed_raw = body.get("password_changed_at")
        password_changed_at = datetime.fromisoformat(password_changed_raw) if password_changed_raw else None
        recent_credential_events = tuple(
            CredentialEvent(event=item["event"], created_at=datetime.fromisoformat(item["created_at"]))
            for item in body.get("recent_credential_events", [])
        )

        return SecurityFacts(
            recent_logins=recent_logins,
            password_changed_at=password_changed_at,
            recent_credential_events=recent_credential_events,
            data_available=True,
        )
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("fraud: security-facts indisponibile (auth-service, user_id=%s): %s", user_id, exc)
        return SecurityFacts(data_available=False)
