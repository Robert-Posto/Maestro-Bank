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
    AccountPublicOut,
    FraudHoldingAccountView,
    InternalAccountView,
    InternalBalanceOut,
    InternalCardSettingsView,
    InternalCreditRequest,
    InternalDebitRequest,
    InternalExchangeRequest,
    InternalExchangeResponse,
    InternalTransferRequest,
    InternalTransferResponse,
    InternalVerifyPinRequest,
    InternalVerifyPinResponse,
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


@router.get("/{account_id}/for-user/{user_id}", response_model=AccountPublicOut)
async def get_account_by_id_internal(account_id: str, user_id: str):
    """Apelat de transactions-service pentru extrasul de cont per-cont
    (userul poate alege orice cont al lui, nu doar "current" — vezi
    generate_account_statement). Reutilizează EXACT
    app/service.py::get_account_by_id_for_user — funcția care deja există
    și e folosită de ruta PUBLICĂ GET /accounts/{account_id} — NU o
    duplică; există special această rută /internal/ doar pentru că
    transactions-service n-are JWT-ul userului, ca să poată apela ruta
    publică direct."""
    return await service.get_account_by_id_for_user(account_id, user_id)


@router.post("/transfer", response_model=InternalTransferResponse)
async def apply_internal_transfer(payload: InternalTransferRequest):
    return await service.apply_internal_transfer(payload.from_account_id, payload.to_account_id, payload.amount_minor)


@router.get("/{account_id}/card-settings", response_model=InternalCardSettingsView)
async def get_account_card_settings(account_id: str):
    """Apelat de transactions-service — vezi
    app/service.py::get_account_card_settings pentru raționamentul
    agregării "oricare card" (alertele/confirmarea la plăți sunt setate
    per-card, dar transferurile MaestroBank sunt cont-la-cont, nu
    card-la-card)."""
    return await service.get_account_card_settings(account_id)


@router.post("/cards/{card_id}/verify-pin", response_model=InternalVerifyPinResponse)
async def verify_card_pin(card_id: str, payload: InternalVerifyPinRequest):
    """Apelat DOAR de transactions-service, cu un `card_id` deja rezolvat
    de get_account_card_settings de mai sus — vezi
    app/service.py::verify_card_pin_internal."""
    return InternalVerifyPinResponse(valid=await service.verify_card_pin_internal(card_id, payload.pin))


@router.post("/exchange", response_model=InternalExchangeResponse)
async def apply_internal_exchange(payload: InternalExchangeRequest):
    return await service.apply_internal_exchange(
        payload.user_id, payload.from_account_type, payload.to_account_type, payload.debit_minor, payload.credit_minor
    )


@router.post("/{account_id}/debit", response_model=InternalBalanceOut)
async def debit_account_internal(account_id: str, payload: InternalDebitRequest):
    """Primitivă GENERICĂ folosită de deposits-service (și, mai târziu, de
    un eventual serviciu de investiții) — vezi app/service.py::debit_account."""
    return await service.debit_account(account_id, payload.amount_minor)


@router.post("/{account_id}/credit", response_model=InternalBalanceOut)
async def credit_account_internal(account_id: str, payload: InternalCreditRequest):
    return await service.credit_account(account_id, payload.amount_minor)


@router.get("/by-user-and-type/{user_id}/{account_type}", response_model=InternalAccountView)
async def get_account_by_user_and_type_internal(user_id: str, account_type: str):
    return await service.get_account_by_user_and_type(user_id, account_type)
