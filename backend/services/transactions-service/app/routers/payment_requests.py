"""Rute protejate (JWT) pentru cereri de plată (link/QR, tip "Request Money",
ca la Revolut) — vezi app/service.py pentru designul complet.

Doar validare (Pydantic/JWT via `CurrentUserId`) și delegare către
app/service.py — logica de business trăiește acolo.

Extern (prin Gateway) acestea devin:
  POST   /api/transactions/payment-requests
  GET    /api/transactions/payment-requests/mine
  GET    /api/transactions/payment-requests/{id}
  POST   /api/transactions/payment-requests/{id}/pay
  POST   /api/transactions/payment-requests/{id}/cancel

ORDINE IMPORTANTĂ: acest router e înregistrat ÎNAINTE de transfers_router
în main.py (la fel ca scheduled_transfers_router, pentru EXACT același
motiv) — altfel POST/GET "/transactions/payment-requests" (un singur
segment sub prefixul "/transactions") ar fi "înghițit" de GET
/{transaction_id} din transfers_router. Ruta literală "/mine" e
înregistrată înaintea wildcard-ului propriu "/{request_id}", din același
motiv de coliziune.
"""

from fastapi import APIRouter, BackgroundTasks, status

from app import service
from app.models import PaymentRequestCreate, PaymentRequestOut, TransactionOut
from app.security import CurrentUserId

router = APIRouter(prefix="/transactions/payment-requests", tags=["payment-requests"])


@router.post("", response_model=PaymentRequestOut, response_model_by_alias=False, status_code=status.HTTP_201_CREATED)
async def create_payment_request(payload: PaymentRequestCreate, user_id: str = CurrentUserId):
    return await service.create_payment_request(user_id, payload)


@router.get("/mine", response_model=list[PaymentRequestOut], response_model_by_alias=False)
async def list_my_payment_requests(user_id: str = CurrentUserId):
    return await service.list_my_payment_requests(user_id)


@router.get("/{request_id}", response_model=PaymentRequestOut, response_model_by_alias=False)
async def get_payment_request(request_id: str, user_id: str = CurrentUserId):
    """Vizualizabilă de ORICE user autentificat, nu doar de cel care a
    creat-o — altfel destinatarul link-ului n-ar putea vedea ce plătește.
    `user_id` e cerut DOAR pentru autentificare (link-ul nu e public —
    vizualizarea tot cere login în MaestroBank, vezi task-ul), nu pentru
    verificare de proprietate."""
    return await service.get_payment_request(request_id, user_id)


@router.post("/{request_id}/pay", response_model=TransactionOut, response_model_by_alias=False)
async def pay_payment_request(request_id: str, background_tasks: BackgroundTasks, user_id: str = CurrentUserId):
    return await service.pay_payment_request(request_id, user_id, background_tasks)


@router.post("/{request_id}/cancel", response_model=PaymentRequestOut, response_model_by_alias=False)
async def cancel_payment_request(request_id: str, user_id: str = CurrentUserId):
    return await service.cancel_payment_request(request_id, user_id)
