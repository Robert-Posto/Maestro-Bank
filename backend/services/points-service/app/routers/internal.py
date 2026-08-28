"""Rute INTERNE ale points-service — DOAR service-to-service. Gateway-ul
blochează explicit orice path care începe cu "internal/" (vezi
backend/gateway/app/routers/proxy.py::_forward), deci nu sunt accesibile din
browser/Angular, indiferent de autentificare.
"""

from fastapi import APIRouter

from app import service
from app.models import CreditForTransactionOut, CreditForTransactionRequest

router = APIRouter(prefix="/internal/points", tags=["internal"])


@router.post("/credit-for-transaction", response_model=CreditForTransactionOut)
async def credit_for_transaction_route(payload: CreditForTransactionRequest):
    """Apelat de transactions-service după fiecare transfer finalizat cu
    succes (best-effort din partea lui) — vezi
    transactions-service/app/service.py::create_transfer."""
    return await service.credit_for_transaction(
        payload.user_id, payload.category, payload.amount_minor, payload.is_merchant_payment
    )
