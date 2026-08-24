"""Rute protejate (JWT) ale verification-service.

Extern (prin Gateway) aceasta devine: POST /api/verification/verify-identity
— vezi backend/gateway/app/routers/proxy.py.
"""

from fastapi import APIRouter, File, UploadFile

from app import service
from app.models import VerificationResult
from app.security import CurrentUserId

router = APIRouter(tags=["verification"])


@router.post("/verify-identity", response_model=VerificationResult)
async def verify_identity(
    id_document: UploadFile = File(...),
    selfie: UploadFile = File(...),
    user_id: str = CurrentUserId,
):
    result = await service.verify_identity(user_id, id_document, selfie)
    return VerificationResult(**result)
