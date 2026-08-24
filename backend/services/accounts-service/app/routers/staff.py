"""Rută pentru PERSONAL — vizualizare READ-ONLY a conturilor unui client
oarecare, în timpul revizuirii unei rețineri de fraudă (staff-holds).
La fel ca transactions-service/app/routers/staff.py: rută NORMALĂ,
protejată cu RequireStaff, la care personalul ajunge din Angular ca un
client obișnuit, doar cu un JWT ce conține role="staff".

Extern (prin Gateway) devine:
  GET /api/accounts/staff/customers/{user_id}/accounts

NOTĂ despre ordine: acest router e înregistrat în main.py ÎNAINTE de
accounts_router (care are GET /{account_id}, wildcard de UN SINGUR
segment) — altfel "staff" ar fi interpretat ca un account_id. Vezi
main.py pentru comentariul complet (același motiv ca /all și /new).
"""

from fastapi import APIRouter

from app import service
from app.models import AccountPublicOut
from app.security import RequireStaff

router = APIRouter(prefix="/staff", tags=["staff"])


@router.get("/customers/{user_id}/accounts", response_model=list[AccountPublicOut])
async def get_customer_accounts(user_id: str, staff_user_id: str = RequireStaff):
    accounts = await service.list_accounts_for_user(user_id)
    return [service.to_public_account(account) for account in accounts]
