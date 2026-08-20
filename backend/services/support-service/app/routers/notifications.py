"""Notificări — istoric persistent, populat de alte servicii.

Două categorii de rute, separate clar:
  - PUBLICE (prin Gateway, JWT): GET /api/support/notifications,
    PATCH /api/support/notifications/read-all — userul vede DOAR
    notificările lui.
  - INTERNE (service-to-service, NU expuse prin Gateway — vezi
    backend/gateway/app/routers/proxy.py, care blochează explicit orice
    path ce începe cu "internal/"): POST /internal/notifications, apelat
    de accounts-service / budgets-service / transactions-service.
"""

from fastapi import APIRouter, status

from app import service
from app.models import NotificationCreate, NotificationOut
from app.security import CurrentUserId

router = APIRouter(prefix="/notifications", tags=["notifications"])
internal_router = APIRouter(prefix="/internal/notifications", tags=["internal"])


@router.get("", response_model=list[NotificationOut], response_model_by_alias=False)
async def list_my_notifications(user_id: str = CurrentUserId):
    return await service.list_notifications_for_user(user_id)


@router.patch("/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_read(user_id: str = CurrentUserId):
    await service.mark_all_read(user_id)


@internal_router.post("", response_model=NotificationOut, response_model_by_alias=False, status_code=status.HTTP_201_CREATED)
async def create_notification(payload: NotificationCreate):
    return await service.create_notification(payload)
