"""Rute protejate (JWT) pentru beneficiari salvați (transfer rapid).

Extern (prin Gateway) acestea devin:
  POST   /api/accounts/beneficiaries
  GET    /api/accounts/beneficiaries
  DELETE /api/accounts/beneficiaries/{id}

Izolare per user obligatorie — un user nu poate vedea/șterge niciodată
beneficiarii altui user (identitatea vine din JWT, nu din input).
"""

from fastapi import APIRouter, status

from app import service
from app.models import BeneficiaryCreate, BeneficiaryOut
from app.security import CurrentUserId

router = APIRouter(prefix="/beneficiaries", tags=["beneficiaries"])


@router.post("", response_model=BeneficiaryOut, response_model_by_alias=False, status_code=status.HTTP_201_CREATED)
async def create_beneficiary(payload: BeneficiaryCreate, user_id: str = CurrentUserId):
    return await service.create_beneficiary(user_id, payload)


@router.get("", response_model=list[BeneficiaryOut], response_model_by_alias=False)
async def list_beneficiaries(user_id: str = CurrentUserId):
    return await service.get_beneficiaries_for_user(user_id)


@router.delete("/{beneficiary_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_beneficiary(beneficiary_id: str, user_id: str = CurrentUserId):
    await service.delete_beneficiary(beneficiary_id, user_id)
