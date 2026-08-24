"""Rute pentru PERSONAL (RequireStaff — app/security.py) — revizuirea
evaluărilor de fraud ȘI rezolvarea hold-urilor active (app/holds.py).
Diferite de routers/internal.py: acelea sunt service-to-service, blocate de
Gateway pentru orice acces din browser; acestea sunt rute NORMALE,
protejate, la care personalul ajunge din Angular exact ca un client
obișnuit, doar cu un JWT ce conține role="staff" (vezi
auth-service/app/security.py::create_access_token).

Extern (prin Gateway) acestea devin:
  GET   /api/transactions/staff/fraud-evaluations
  GET   /api/transactions/staff/fraud-evaluations/{id}
  PATCH /api/transactions/staff/fraud-evaluations/{id}/review
  GET   /api/transactions/staff/holds
  POST  /api/transactions/staff/holds/{id}/approve
  POST  /api/transactions/staff/holds/{id}/reject
  GET   /api/transactions/staff/customers/{user_id}/transactions
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Query

from app import holds, service
from app.fraud import staff as staff_service
from app.models import (
    FraudEvaluationOut,
    FraudEvaluationReviewRequest,
    HoldResolutionOut,
    StaffHoldOut,
    TransactionOut,
)
from app.security import RequireStaff

router = APIRouter(prefix="/transactions/staff", tags=["staff"])


@router.get("/fraud-evaluations", response_model=list[FraudEvaluationOut], response_model_by_alias=False)
async def list_fraud_evaluations(
    decision_band: str | None = Query(default=None),
    reviewed: bool | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    staff_user_id: str = RequireStaff,
):
    return await staff_service.list_evaluations(
        decision_band=decision_band, reviewed=reviewed, since=since, until=until, limit=limit, skip=skip
    )


@router.get("/fraud-evaluations/{evaluation_id}", response_model=FraudEvaluationOut, response_model_by_alias=False)
async def get_fraud_evaluation(evaluation_id: str, staff_user_id: str = RequireStaff):
    return await staff_service.get_evaluation(evaluation_id)


@router.patch(
    "/fraud-evaluations/{evaluation_id}/review", response_model=FraudEvaluationOut, response_model_by_alias=False
)
async def review_fraud_evaluation(
    evaluation_id: str, payload: FraudEvaluationReviewRequest, staff_user_id: str = RequireStaff
):
    return await staff_service.review_evaluation(
        evaluation_id=evaluation_id,
        staff_user_id=staff_user_id,
        outcome=payload.outcome,
        note=payload.note,
        # reviewed_at e bookkeeping operațional (ca fraud_evaluations.created_at
        # din audit.py), nu intră niciodată în aritmetică de determinism —
        # aware e ok aici, spre deosebire de evaluated_at (vezi timeutil.py).
        reviewed_at=datetime.now(timezone.utc),
    )


@router.get("/holds", response_model=list[StaffHoldOut])
async def list_holds(staff_user_id: str = RequireStaff):
    return await holds.list_pending_holds()


@router.post("/holds/{transaction_id}/approve", response_model=HoldResolutionOut, response_model_by_alias=False)
async def approve_hold(transaction_id: str, staff_user_id: str = RequireStaff):
    doc = await holds.approve_hold(transaction_id, staff_user_id)
    return HoldResolutionOut.from_transaction_doc(doc)


@router.post("/holds/{transaction_id}/reject", response_model=HoldResolutionOut, response_model_by_alias=False)
async def reject_hold(transaction_id: str, staff_user_id: str = RequireStaff):
    doc = await holds.reject_hold(transaction_id, staff_user_id)
    return HoldResolutionOut.from_transaction_doc(doc)


@router.get(
    "/customers/{user_id}/transactions",
    response_model=list[TransactionOut],
    response_model_by_alias=False,
)
async def get_customer_transactions(
    user_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    staff_user_id: str = RequireStaff,
):
    """READ-ONLY — istoricul de tranzacții al unui client oarecare, pentru
    personalul care revizuiește un hold și vrea contextul complet (nu doar
    tranzacția care a declanșat reținerea). Reutilizează EXACT
    service.list_transactions_for_user, care oricum ia user_id ca parametru
    simplu (nu-l derivă din JWT) — funcționează identic pentru orice user_id,
    fie userul propriu (ruta normală, /transactions), fie unul arbitrar
    (aici, gatat de RequireStaff)."""
    return await service.list_transactions_for_user(user_id, limit, skip)
