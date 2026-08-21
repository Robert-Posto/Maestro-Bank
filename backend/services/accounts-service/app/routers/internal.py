"""Endpoint-uri INTERNE ale accounts-service.

Apelabile DOAR container-to-container (de auth-service și
transactions-service), folosind adresa internă Docker
`http://accounts-service:8000`. NU sunt expuse prin API Gateway —
gateway blochează explicit orice path care începe cu "internal/" (vezi
backend/gateway/app/routers/proxy.py), tocmai ca aceste rute să nu poată
fi apelate din browser/Angular.

Doar validare și delegare către app/service.py — logica de business
trăiește acolo.
"""

from fastapi import APIRouter, status

from app import service
from app.models import (
    FraudHoldingAccountView,
    InternalAccountView,
    InternalTransferRequest,
    InternalTransferResponse,
    ProvisionRequest,
    ProvisionResponse,
)

router = APIRouter(prefix="/internal/accounts", tags=["internal"])


@router.post("/provision", response_model=ProvisionResponse, status_code=status.HTTP_201_CREATED)
async def provision_account(payload: ProvisionRequest):
    account, card = await service.provision_account(payload.user_id)
    return ProvisionResponse(account=account, card=card)


@router.get("/fraud-holding-account", response_model=FraudHoldingAccountView)
async def get_fraud_holding_account():
    return FraudHoldingAccountView(account_id=await service.get_fraud_holding_account_id())


@router.get("/by-user/{user_id}", response_model=InternalAccountView)
async def get_account_by_user(user_id: str):
    return await service.get_account_by_user(user_id)


@router.get("/by-iban/{iban}", response_model=InternalAccountView)
async def get_account_by_iban(iban: str):
    return await service.get_account_by_iban(iban)


@router.post("/transfer", response_model=InternalTransferResponse)
async def apply_internal_transfer(payload: InternalTransferRequest):
    return await service.apply_internal_transfer(payload.from_account_id, payload.to_account_id, payload.amount_minor)
