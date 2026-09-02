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
from app.i18n import translate
from app.models import (
    EligibilitySnapshotOut,
    LoanApplicantContact,
    LoanApplicationStaffOut,
    LoanApplyRequest,
    LoanOut,
    LoanPaymentOut,
)
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
                status_code=status.HTTP_502_BAD_GATEWAY, detail=translate("accountsServiceUnavailable")
            ) from exc
    if response.status_code == 404:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=translate("currentAccountNotFound"))
    if response.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=translate("accountsServiceQueryError"))
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
                status_code=status.HTTP_502_BAD_GATEWAY, detail=translate("accountsServiceUnavailable")
            ) from exc
    if response.status_code == 409:
        return False
    if response.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=translate("accountDebitError"))
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
                status_code=status.HTTP_502_BAD_GATEWAY, detail=translate("accountsServiceUnavailable")
            ) from exc
    if response.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=translate("accountCreditError"))


async def _notify_user(
    user_id: str, kind: str, message_key: str, message_params: dict | None = None, reference_id: str | None = None
) -> None:
    """Best-effort. Trimite `message_key` + `message_params` (valori BRUTE) —
    support-service randează textul în limba CITITORULUI la fiecare citire
    (vezi support-service/app/i18n.py::render_notification), deci notificarea
    își schimbă limba la comutarea comutatorului, retroactiv."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post(
                f"{settings.support_service_url}/internal/notifications",
                json={
                    "user_id": user_id,
                    "kind": kind,
                    "message_key": message_key,
                    "message_params": message_params or {},
                    "reference_id": reference_id,
                },
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
        applied_at=doc["applied_at"],
        opened_at=doc.get("opened_at"),
        next_payment_due_at=doc.get("next_payment_due_at"),
        status=doc["status"],
        paid_off_at=doc.get("paid_off_at"),
        rejection_reason=doc.get("rejection_reason"),
        application=doc["application"],
    )


def _to_staff_out(doc: dict, applicant: LoanApplicantContact | None) -> LoanApplicationStaffOut:
    return LoanApplicationStaffOut(
        id=str(doc["_id"]),
        user_id=doc["user_id"],
        applicant=applicant,
        principal_minor=doc["principal_minor"],
        term_months=doc["term_months"],
        rate_percent_annual=doc["rate_percent_annual"],
        monthly_installment_minor=doc["monthly_installment_minor"],
        applied_at=doc["applied_at"],
        status=doc["status"],
        application=doc["application"],
        eligibility=EligibilitySnapshotOut(**doc["eligibility_snapshot"]),
        rejection_reason=doc.get("rejection_reason"),
        reviewed_by=doc.get("reviewed_by"),
        reviewed_at=doc.get("reviewed_at"),
    )


async def _fetch_user_contact(user_id: str) -> LoanApplicantContact | None:
    """Best-effort — identic ca tipar cu transactions-service/app/holds.py
    ::_fetch_user_contact. Un ecran de personal fără numele clientului tot
    e util (id-ul rămâne vizibil), deci nu blocăm lista dacă auth-service
    e temporar indisponibil."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.get(f"{settings.auth_service_url}/internal/users/{user_id}/contact")
        except httpx.RequestError:
            return None
    if response.status_code != 200:
        return None
    return LoanApplicantContact(**response.json())


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


async def submit_loan_application(user_id: str, payload: LoanApplyRequest) -> LoanOut:
    """Depune o cerere de credit — NU mai acordă bani pe loc (spre
    deosebire de vechiul apply_for_loan). Verificarea de eligibilitate încă
    rulează AICI, o singură dată, pe date reale — dar rezultatul devine o
    RECOMANDARE atașată cererii (`eligibility_snapshot`), afișată
    personalului la revizuire, nu o respingere automată. Decizia finală
    aparține STRICT personalului (vezi approve_application/reject_application
    mai jos) — exact fluxul unei bănci reale, unde un scor automat
    informează un ofițer de credit, nu decide singur."""
    if payload.amount_minor < MIN_LOAN_MINOR or payload.amount_minor > MAX_LOAN_MINOR:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=translate("amountOutOfRange", min=f"{MIN_LOAN_MINOR / 100:.2f}", max=f"{MAX_LOAN_MINOR / 100:.2f}"),
        )

    rate = get_rate(payload.term_months)
    monthly_installment_minor = compute_monthly_installment_minor(payload.amount_minor, rate, payload.term_months)

    existing_installments_minor = await _sum_active_installments(user_id)
    eligibility: EligibilityResult = await evaluate_eligibility(user_id, existing_installments_minor)
    total_installments_minor = monthly_installment_minor + existing_installments_minor
    recommended = total_installments_minor <= eligibility.max_affordable_installment_minor
    eligibility_snapshot = {
        "average_monthly_income_minor": eligibility.average_monthly_income_minor,
        "max_affordable_installment_minor": eligibility.max_affordable_installment_minor,
        "existing_installments_minor": eligibility.existing_installments_minor,
        "recommended": recommended,
        "reason": None if recommended else render_rejection_reason(eligibility, monthly_installment_minor),
    }

    # Verificăm contul curent acum (există?), dar NU-l credităm încă — abia
    # la approve_application, când personalul chiar aprobă cererea.
    account = await _get_current_account(user_id)

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
        "applied_at": now,
        "opened_at": None,
        "next_payment_due_at": None,
        "status": "pending_review",
        "paid_off_at": None,
        "rejection_reason": None,
        "application": payload.application.model_dump(),
        "eligibility_snapshot": eligibility_snapshot,
        "reviewed_by": None,
        "reviewed_at": None,
    }
    result = await get_database().loans.insert_one(doc)
    doc["_id"] = result.inserted_id
    logger.info(
        "loans-service: cerere depusă (id=%s, user_id=%s, suma=%s, termen=%s luni, recomandare=%s)",
        result.inserted_id,
        user_id,
        payload.amount_minor,
        payload.term_months,
        recommended,
    )
    return _to_loan_out(doc)


async def _get_pending_application_by_id(application_id: str) -> dict:
    try:
        oid = ObjectId(application_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=translate("loanNotFound")) from exc
    doc = await get_database().loans.find_one({"_id": oid})
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=translate("loanNotFound"))
    if doc["status"] != "pending_review":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=translate("applicationNoLongerPending"))
    return doc


async def list_pending_applications() -> list[LoanApplicationStaffOut]:
    """Pentru personal — vezi routers/staff.py. Cererile în așteptare,
    cele mai vechi primele (FIFO, ca la o coadă de evaluare reală)."""
    db = get_database()
    docs = await db.loans.find({"status": "pending_review"}).sort("applied_at", 1).to_list(length=200)
    results = []
    for doc in docs:
        applicant = await _fetch_user_contact(doc["user_id"])
        results.append(_to_staff_out(doc, applicant))
    return results


async def approve_application(application_id: str, staff_user_id: str) -> LoanApplicationStaffOut:
    """Aprobă o cerere — ABIA acum se acordă banii (credit real pe contul
    curent), exact ca la vechiul apply_for_loan, dar declanșat de personal,
    nu automat la depunere."""
    doc = await _get_pending_application_by_id(application_id)
    await _credit_account(doc["account_id"], doc["principal_minor"])

    now = datetime.now(timezone.utc)
    update = {
        "status": "active",
        "opened_at": now,
        "next_payment_due_at": now + timedelta(days=_INSTALLMENT_INTERVAL_DAYS),
        "reviewed_by": staff_user_id,
        "reviewed_at": now,
    }
    await get_database().loans.update_one({"_id": doc["_id"]}, {"$set": update})
    doc.update(update)
    logger.info(
        "loans-service: cerere aprobată (id=%s, user_id=%s, staff=%s, suma=%s)",
        application_id,
        doc["user_id"],
        staff_user_id,
        doc["principal_minor"],
    )
    await _notify_user(
        doc["user_id"],
        "loan_approved",
        "loanApproved",
        {
            "amount_minor": doc["principal_minor"],
            "instalment_minor": doc["monthly_installment_minor"],
            "months": doc["term_months"],
        },
        reference_id=str(doc["_id"]),
    )
    applicant = await _fetch_user_contact(doc["user_id"])
    return _to_staff_out(doc, applicant)


async def reject_application(application_id: str, staff_user_id: str, reason: str) -> LoanApplicationStaffOut:
    """Respinge o cerere — NICIUN ban nu s-a mișcat vreodată (banii se
    acordă STRICT la aprobare), deci nu există nimic de anulat/rollback."""
    doc = await _get_pending_application_by_id(application_id)

    now = datetime.now(timezone.utc)
    update = {
        "status": "rejected",
        "rejection_reason": reason,
        "reviewed_by": staff_user_id,
        "reviewed_at": now,
    }
    await get_database().loans.update_one({"_id": doc["_id"]}, {"$set": update})
    doc.update(update)
    logger.info(
        "loans-service: cerere respinsă (id=%s, user_id=%s, staff=%s)",
        application_id,
        doc["user_id"],
        staff_user_id,
    )
    await _notify_user(
        doc["user_id"],
        "loan_rejected",
        "loanRejected",
        {"reason": reason},
        reference_id=str(doc["_id"]),
    )
    applicant = await _fetch_user_contact(doc["user_id"])
    return _to_staff_out(doc, applicant)


async def list_my_loans(user_id: str) -> list[LoanOut]:
    # sortăm după applied_at, NU opened_at — o cerere "pending_review"/
    # "rejected" n-are opened_at (setat DOAR la aprobare, vezi
    # approve_application), dar are mereu applied_at.
    cursor = get_database().loans.find({"user_id": user_id}).sort("applied_at", -1)
    docs = await cursor.to_list(length=200)
    return [_to_loan_out(doc) for doc in docs]


async def _get_own_loan(loan_id: str, user_id: str) -> dict:
    try:
        oid = ObjectId(loan_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=translate("loanNotFound")) from exc
    doc = await get_database().loans.find_one({"_id": oid, "user_id": user_id})
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=translate("loanNotFound"))
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
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=translate("loanNoLongerActive"))

    payoff_amount_minor = doc["outstanding_principal_minor"]
    succeeded = await _debit_account(doc["account_id"], payoff_amount_minor)
    if not succeeded:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=translate("insufficientBalanceForPayoff"))

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
        "loanPaidOffEarly",
        {"amount_minor": payoff_amount_minor},
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
                "loanPaymentMissed",
                {"amount_minor": amount_minor},
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
            "loanPayment",
            {"amount_minor": amount_minor},
            reference_id=str(doc["_id"]),
        )
        if now_paid_off:
            await _notify_user(
                doc["user_id"],
                "loan_paid_off",
                "loanClosed",
                reference_id=str(doc["_id"]),
            )
        processed += 1

    return processed
