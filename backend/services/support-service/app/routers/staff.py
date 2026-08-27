"""Rute pentru PERSONAL — căutare clienți + trimitere/gestionare documente
de semnat (eSign). La fel ca accounts-service/app/routers/staff.py:
rute NORMALE, protejate cu RequireStaff, la care personalul ajunge din
Angular ca un client obișnuit, doar cu un JWT ce conține role="staff".

Extern (prin Gateway) acestea devin:
  GET    /api/support/staff/customers/search?q=...
  POST   /api/support/staff/documents
  GET    /api/support/staff/documents
  DELETE /api/support/staff/documents/{id}

NOTĂ despre ordine: fără conflict de rută cu routers/documents.py — prefixele
sunt distincte (`/staff/*` vs `/documents/*`), deci ordinea de înregistrare
în main.py nu contează aici (spre deosebire de accounts-service, unde
/staff ar coliziona cu un wildcard de un singur segment).
"""

from fastapi import APIRouter, Query, status

from app import service
from app.models import DocumentCreate, StaffCustomerSearchResult, StaffDocumentOut
from app.security import RequireStaff

router = APIRouter(prefix="/staff", tags=["staff"])


@router.get("/customers/search", response_model=list[StaffCustomerSearchResult])
async def search_customers(q: str = "", staff_user_id: str = RequireStaff):
    return await service.search_customers(q)


@router.post("/documents", response_model=StaffDocumentOut, response_model_by_alias=False, status_code=status.HTTP_201_CREATED)
async def send_document(payload: DocumentCreate, staff_user_id: str = RequireStaff):
    return await service.create_document(payload, staff_user_id)


@router.get("/documents", response_model=list[StaffDocumentOut], response_model_by_alias=False)
async def list_sent_documents(
    limit: int = Query(default=100, ge=1, le=100), skip: int = Query(default=0, ge=0), staff_user_id: str = RequireStaff
):
    return await service.list_documents_for_staff(limit, skip)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_document(document_id: str, staff_user_id: str = RequireStaff):
    await service.cancel_document(document_id, staff_user_id)
