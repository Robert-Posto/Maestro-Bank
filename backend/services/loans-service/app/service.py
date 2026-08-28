"""Logica de business a loans-service.

Separată de routing (app/routers/*.py) și modele (app/models.py). Acest
modul e singurul care atinge db.loans/db.loan_payments direct.

loans-service NU citește niciodată direct accounts_db/tx_db — orice mișcare
de bani trece prin API-ul intern al accounts-service (debit/credit pe UN
cont), iar verificarea de eligibilitate trage istoricul REAL de tranzacții
prin API-ul intern al transactions-service — vezi app/eligibility.py.
"""

import logging
from datetime import datetime, timedelta, timezone

import httpx
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status

from app.config import settings
from app.database import get_database
from app.eligibility import EligibilityResult, evaluate_eligibility, render_rejection_reason
from app.models import LoanApplyRequest, LoanOut, LoanPaymentOut
from app.rates import MAX_LOAN_MINOR, MIN_LOAN_MINOR, compute_monthly_installment_minor, get_rate

logger = logging.getLogger("loans-service")

_RETRY_AFTER_MISSED_PAYMENT_DAYS = 1
_INSTALLMENT_INTERVAL_DAYS = 30


async def _get_current_account(user_id: str) -> dict:
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.get(
                f"{settings.accounts_service_url}/internal/accounts/by-user-and-type/{user_id}/current"
            )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail="accounts-service indisponibil."
            ) from exc
    if response.status_code == 404:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nu am găsit contul tău curent.")
    if response.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Eroare la interogarea accounts-service.")
    return response.json()


async def _debit_account(account_id: str, amount_minor: int) -> bool:
    """Întoarce False (NU aruncă) la 409 — folosită și din scheduler, unde
    sold insuficient e un caz normal de gestionat, nu o eroare de propagat
    ca HTTPException."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.post(
                f"{settings.accounts_service_url}/internal/accounts/{account_id}/debit",
                json={"amount_minor": amount_minor},
            )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail="accounts-service indisponibil."
            ) from exc
    if response.status_code == 409:
        return False
    if response.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Eroare la debitarea contului.")
    return True


async def _credit_account(account_id: str, amount_minor: int) -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.post(
                f"{settings.accounts_service_url}/internal/accounts/{account_id}/credit",
                json={"amount_minor": amount_minor},
            )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail="accounts-service indisponibil."
            ) from exc
    if response.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Eroare la creditarea contului.")


async def _notify_user(user_id: str, kind: str, text: str, reference_id: str | None = None) -> None:
    """Best-effort — la fel ca _notify_user din transactions-service/points-service."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post(
                f"{settings.support_service_url}/internal/notifications",
                json={"user_id": user_id, "kind": kind, "text": text, "reference_id": reference_id},
            )
    except httpx.HTTPError:
        logger.warning("loans-service: notificare eșuată (user_id=%s, kind=%s)", user_id, kind)


def _to_loan_out(doc: dict) -> LoanOut:
    return LoanOut(
        id=str(doc["_id"]),
        principal_minor=doc["principal_minor"],
        outstanding_principal_minor=doc["outstanding_principal_minor"],
        term_months=doc["term_months"],
        rate_percent_annual=doc["rate_percent_annual"],
        monthly_installment_minor=doc["monthly_installment_minor"],
        payments_made=doc["payments_made"],
        opened_at=doc["opened_at"],
        next_payment_due_at=doc.get("next_payment_due_at"),
        status=doc["status"],
        paid_off_at=doc.get("paid_off_at"),
    )


def _to_payment_out(doc: dict) -> LoanPaymentOut:
    return LoanPaymentOut(
        id=str(doc["_id"]),
        loan_id=doc["loan_id"],
        paid_at=doc["paid_at"],
        amount_minor=doc["amount_minor"],
        interest_portion_minor=doc["interest_portion_minor"],
        principal_portion_minor=doc["principal_portion_minor"],
        outstanding_after_minor=doc["outstanding_after_minor"],
    )


async def _sum_active_installments(user_id: str) -> int:
    db = get_database()
    cursor = db.loans.find({"user_id": user_id, "status": "active"})
    docs = await cursor.to_list(length=200)
    return sum(doc["monthly_installment_minor"] for doc in docs)


async def apply_for_loan(user_id: str, payload: LoanApplyRequest) -> LoanOut:
    if payload.amount_minor < MIN_LOAN_MINOR or payload.amount_minor > MAX_LOAN_MINOR:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Suma trebuie să fie între {MIN_LOAN_MINOR / 100:.2f} și {MAX_LOAN_MINOR / 100:.2f} RON.",
        )

    rate = get_rate(payload.term_months)
    monthly_installment_minor = compute_monthly_installment_minor(payload.amount_minor, rate, payload.term_months)

    existing_installments_minor = await _sum_active_installments(user_id)
    eligibility: EligibilityResult = await evaluate_eligibility(user_id, existing_installments_minor)
    total_installments_minor = monthly_installment_minor + existing_installments_minor
    if total_installments_minor > eligibility.max_affordable_installment_minor:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=render_rejection_reason(eligibility, monthly_installment_minor),
        )

    account = await _get_current_account(user_id)
    await _credit_account(account["id"], payload.amount_minor)

    now = datetime.now(timezone.utc)
    doc = {
        "user_id": user_id,
        "account_id": account["id"],
        "principal_minor": payload.amount_minor,
        "outstanding_principal_minor": payload.amount_minor,
        "term_months": payload.term_months,
        "rate_percent_annual": rate,
        "monthly_installment_minor": monthly_installment_minor,
        "payments_made": 0,
        "missed_payments_count": 0,
        "opened_at": now,
        "next_payment_due_at": now + timedelta(days=_INSTALLMENT_INTERVAL_DAYS),
        "status": "active",
        "paid_off_at": None,
    }
    result = await get_database().loans.insert_one(doc)
    doc["_id"] = result.inserted_id
    logger.info(
        "loans-service: credit aprobat (id=%s, user_id=%s, suma=%s, termen=%s luni, rata=%s)",
        result.inserted_id,
        user_id,
        payload.amount_minor,
        payload.term_months,
        monthly_installment_minor,
    )
    await _notify_user(
        user_id,
        "loan_approved",
        f"Creditul tău de {payload.amount_minor / 100:.2f} lei a fost aprobat — rata lunară e "
        f"{monthly_installment_minor / 100:.2f} lei, pe {payload.term_months} luni.",
        reference_id=str(result.inserted_id),
    )
    return _to_loan_out(doc)


async def list_my_loans(user_id: str) -> list[LoanOut]:
    cursor = get_database().loans.find({"user_id": user_id}).sort("opened_at", -1)
    docs = await cursor.to_list(length=200)
    return [_to_loan_out(doc) for doc in docs]


async def _get_own_loan(loan_id: str, user_id: str) -> dict:
    try:
        oid = ObjectId(loan_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credit inexistent.") from exc
    doc = await get_database().loans.find_one({"_id": oid, "user_id": user_id})
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credit inexistent.")
    return doc


async def list_payments(loan_id: str, user_id: str) -> list[LoanPaymentOut]:
    await _get_own_loan(loan_id, user_id)  # doar ca să confirmăm ownership-ul (404 dacă nu-i al userului)
    cursor = get_database().loan_payments.find({"loan_id": loan_id}).sort("paid_at", -1)
    docs = await cursor.to_list(length=500)
    return [_to_payment_out(doc) for doc in docs]


async def payoff_loan(loan_id: str, user_id: str) -> LoanOut:
    """Plată anticipată — achită DOAR principalul rămas, fără dobândă
    suplimentară pentru perioada parțială (simplificare documentată, în
    avantajul clientului — la fel ca lichidarea unui depozit)."""
    doc = await _get_own_loan(loan_id, user_id)
    if doc["status"] != "active":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Creditul nu mai este activ.")

    payoff_amount_minor = doc["outstanding_principal_minor"]
    succeeded = await _debit_account(doc["account_id"], payoff_amount_minor)
    if not succeeded:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Sold insuficient pentru plata anticipată.")

    now = datetime.now(timezone.utc)
    db = get_database()
    await db.loans.update_one(
        {"_id": doc["_id"]},
        {"$set": {"status": "paid_off", "outstanding_principal_minor": 0, "paid_off_at": now, "next_payment_due_at": None}},
    )
    await db.loan_payments.insert_one(
        {
            "loan_id": loan_id,
            "user_id": user_id,
            "paid_at": now,
            "amount_minor": payoff_amount_minor,
            "interest_portion_minor": 0,
            "principal_portion_minor": payoff_amount_minor,
            "outstanding_after_minor": 0,
        }
    )
    doc.update(status="paid_off", outstanding_principal_minor=0, paid_off_at=now, next_payment_due_at=None)
    logger.info("loans-service: plată anticipată (id=%s, user_id=%s, suma=%s)", loan_id, user_id, payoff_amount_minor)
    await _notify_user(
        user_id,
        "loan_paid_off",
        f"Ai plătit anticipat restul de {payoff_amount_minor / 100:.2f} lei — creditul e închis.",
        reference_id=loan_id,
    )
    return _to_loan_out(doc)


def _split_installment(
    *, outstanding_principal_minor: int, rate_percent_annual: float, monthly_installment_minor: int, is_final: bool
) -> tuple[int, int]:
    """Împarte o rată în (dobândă, principal) — dobânda pe soldul rămas
    (aceeași rată lunară folosită la calculul ratei inițiale, vezi
    app/rates.py::compute_monthly_installment_minor), restul e principal.
    Funcție PURĂ (fără DB), testabilă direct — extrasă din
    process_due_payments ca să nu fie nevoie de Mongo ca s-o verifici.

    Ultima rată din scadențar (`is_final`) închide EXACT soldul rămas, nu
    suma fixă a ratei — altfel ar rămâne un rest din rotunjiri și
    împrumutul nu s-ar închide niciodată la 0."""
    interest_portion = round(outstanding_principal_minor * rate_percent_annual / 12 / 100)
    if is_final:
        principal_portion = outstanding_principal_minor
    else:
        principal_portion = min(monthly_installment_minor - interest_portion, outstanding_principal_minor)
    return interest_portion, principal_portion


async def process_due_payments() -> int:
    """Apelat periodic de scheduler — vezi app/scheduler.py. Găsește
    creditele active cu rata scadentă și încearcă debitarea. Întoarce câte
    a procesat (reușite SAU ratate — ambele sunt "procesate")."""
    db = get_database()
    now = datetime.now(timezone.utc)
    cursor = db.loans.find({"status": "active", "next_payment_due_at": {"$lte": now}})
    due = await cursor.to_list(length=500)

    processed = 0
    for doc in due:
        is_final = doc["payments_made"] + 1 >= doc["term_months"]
        interest_portion, principal_portion = _split_installment(
            outstanding_principal_minor=doc["outstanding_principal_minor"],
            rate_percent_annual=doc["rate_percent_annual"],
            monthly_installment_minor=doc["monthly_installment_minor"],
            is_final=is_final,
        )
        amount_minor = interest_portion + principal_portion

        succeeded = await _debit_account(doc["account_id"], amount_minor)
        if not succeeded:
            await db.loans.update_one(
                {"_id": doc["_id"]},
                {
                    "$set": {"next_payment_due_at": now + timedelta(days=_RETRY_AFTER_MISSED_PAYMENT_DAYS)},
                    "$inc": {"missed_payments_count": 1},
                },
            )
            logger.warning("loans-service: rată ratată, sold insuficient (id=%s, user_id=%s)", doc["_id"], doc["user_id"])
            await _notify_user(
                doc["user_id"],
                "loan_payment_missed",
                f"Rata de {amount_minor / 100:.2f} lei nu a putut fi plătită — sold insuficient. Reîncercăm automat.",
                reference_id=str(doc["_id"]),
            )
            processed += 1
            continue

        outstanding_after = doc["outstanding_principal_minor"] - principal_portion
        payments_made = doc["payments_made"] + 1
        now_paid_off = outstanding_after <= 0 or payments_made >= doc["term_months"]

        update: dict = {
            "outstanding_principal_minor": max(outstanding_after, 0),
            "payments_made": payments_made,
        }
        if now_paid_off:
            update.update(status="paid_off", paid_off_at=now, next_payment_due_at=None)
        else:
            update["next_payment_due_at"] = now + timedelta(days=_INSTALLMENT_INTERVAL_DAYS)
        await db.loans.update_one({"_id": doc["_id"]}, {"$set": update})

        await db.loan_payments.insert_one(
            {
                "loan_id": str(doc["_id"]),
                "user_id": doc["user_id"],
                "paid_at": now,
                "amount_minor": amount_minor,
                "interest_portion_minor": interest_portion,
                "principal_portion_minor": principal_portion,
                "outstanding_after_minor": max(outstanding_after, 0),
            }
        )
        logger.info(
            "loans-service: rată plătită (id=%s, user_id=%s, suma=%s, rest=%s)",
            doc["_id"],
            doc["user_id"],
            amount_minor,
            max(outstanding_after, 0),
        )
        await _notify_user(
            doc["user_id"],
            "loan_payment",
            f"Rata de {amount_minor / 100:.2f} lei a fost plătită automat.",
            reference_id=str(doc["_id"]),
        )
        if now_paid_off:
            await _notify_user(
                doc["user_id"],
                "loan_paid_off",
                "Ultima rată a fost plătită — creditul e închis.",
                reference_id=str(doc["_id"]),
            )
        processed += 1

    return processed
