"""Rute protejate (JWT) pentru documentele de semnat (eSign) — client-facing.

Extern (prin Gateway) acestea devin:
  GET  /api/support/documents
  GET  /api/support/documents/{id}
  POST /api/support/documents/{id}/sign

Userul vede/semnează DOAR propriile documente — identitatea vine din JWT,
la fel ca la tichete (vezi routers/support.py).
"""

from fastapi import APIRouter

from app import service
from app.models import DocumentOut, DocumentSignRequest, DocumentSummaryOut
from app.security import CurrentUserId

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=list[DocumentSummaryOut], response_model_by_alias=False)
async def list_my_documents(user_id: str = CurrentUserId):
    return await service.list_documents_for_user(user_id)


@router.get("/{document_id}", response_model=DocumentOut, response_model_by_alias=False)
async def get_document(document_id: str, user_id: str = CurrentUserId):
    return await service.get_document_for_user(document_id, user_id)


@router.post("/{document_id}/sign", response_model=DocumentSummaryOut, response_model_by_alias=False)
async def sign_document(document_id: str, payload: DocumentSignRequest, user_id: str = CurrentUserId):
    return await service.sign_document(document_id, user_id, payload)
