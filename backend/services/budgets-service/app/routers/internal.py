"""Endpoint-uri INTERNE ale budgets-service.

Apelabile DOAR container-to-container (de transactions-service, pentru
forecast — vezi transactions-service/app/service.py::_get_subscriptions_for_user),
folosind adresa internă Docker `http://budgets-service:8000`. NU sunt
expuse prin API Gateway — gateway blochează explicit orice path care
începe cu "internal/" (vezi backend/gateway/app/routers/proxy.py).
"""

from fastapi import APIRouter

from app import service
from app.models import InternalSubscriptionView

router = APIRouter(prefix="/internal/budgets", tags=["internal"])


@router.get("/subscriptions/by-user/{user_id}", response_model=list[InternalSubscriptionView])
async def get_active_subscriptions_by_user(user_id: str):
    return await service.get_active_subscriptions_for_user_internal(user_id)
