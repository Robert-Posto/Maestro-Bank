"""Rute protejate (JWT) ale loans-service.

Doar validare și delegare către app/service.py — logica de business
trăiește acolo.

Extern (prin Gateway) acestea devin:
  GET  /api/loans/rates
  POST /api/loans/apply
  GET  /api/loans
  GET  /api/loans/{id}/payments
  POST /api/loans/{id}/payoff
"""

from fastapi import APIRouter

from app import service
from app.models import LoanApplyRequest, LoanOut, LoanPaymentOut, LoanRateOut
from app.rates import list_rates
from app.security import CurrentUserId

router = APIRouter(prefix="/loans", tags=["loans"])


@router.get("/rates", response_model=list[LoanRateOut])
async def get_rates(user_id: str = CurrentUserId):
    return list_rates()


@router.post("/apply", response_model=LoanOut, status_code=201)
async def apply_for_loan_route(payload: LoanApplyRequest, user_id: str = CurrentUserId):
    return await service.apply_for_loan(user_id, payload)


@router.get("", response_model=list[LoanOut])
async def list_my_loans_route(user_id: str = CurrentUserId):
    return await service.list_my_loans(user_id)


@router.get("/{loan_id}/payments", response_model=list[LoanPaymentOut])
async def list_payments_route(loan_id: str, user_id: str = CurrentUserId):
    return await service.list_payments(loan_id, user_id)


@router.post("/{loan_id}/payoff", response_model=LoanOut)
async def payoff_loan_route(loan_id: str, user_id: str = CurrentUserId):
    return await service.payoff_loan(loan_id, user_id)
