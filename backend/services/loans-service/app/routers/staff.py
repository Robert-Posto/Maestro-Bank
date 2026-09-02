"""Rute pentru PERSONAL (RequireStaff — app/security.py) — revizuirea
cererilor de credit în așteptare. Identic ca tipar cu
transactions-service/app/routers/staff.py (holds).

Extern (prin Gateway) acestea devin:
  GET  /api/loans/staff/applications
  POST /api/loans/staff/applications/{id}/approve
  POST /api/loans/staff/applications/{id}/reject
"""

from fastapi import APIRouter

from app import service
from app.models import LoanApplicationRejectRequest, LoanApplicationStaffOut
from app.security import RequireStaff

router = APIRouter(prefix="/loans/staff", tags=["loans-staff"])


@router.get("/applications", response_model=list[LoanApplicationStaffOut])
async def list_applications_route(staff_user_id: str = RequireStaff):
    return await service.list_pending_applications()


@router.post("/applications/{application_id}/approve", response_model=LoanApplicationStaffOut)
async def approve_application_route(application_id: str, staff_user_id: str = RequireStaff):
    return await service.approve_application(application_id, staff_user_id)


@router.post("/applications/{application_id}/reject", response_model=LoanApplicationStaffOut)
async def reject_application_route(
    application_id: str, payload: LoanApplicationRejectRequest, staff_user_id: str = RequireStaff
):
    return await service.reject_application(application_id, staff_user_id, payload.reason)
