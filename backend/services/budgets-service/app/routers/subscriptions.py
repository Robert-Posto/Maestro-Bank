"""Rute protejate (JWT) pentru abonamente / plăți recurente.

Extern (prin Gateway) acestea devin:
  POST   /api/budgets/subscriptions
  GET    /api/budgets/subscriptions
  PATCH  /api/budgets/subscriptions/{id}
  DELETE /api/budgets/subscriptions/{id}
"""

from fastapi import APIRouter, status

from app import service
from app.models import SubscriptionCreate, SubscriptionOut, SubscriptionUpdate
from app.security import CurrentUserId

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@router.post("", response_model=SubscriptionOut, response_model_by_alias=False, status_code=status.HTTP_201_CREATED)
async def create_subscription(payload: SubscriptionCreate, user_id: str = CurrentUserId):
    return await service.create_subscription(user_id, payload)


@router.get("", response_model=list[SubscriptionOut], response_model_by_alias=False)
async def list_subscriptions(user_id: str = CurrentUserId):
    return await service.list_subscriptions_for_user(user_id)


@router.patch("/{subscription_id}", response_model=SubscriptionOut, response_model_by_alias=False)
async def update_subscription(subscription_id: str, payload: SubscriptionUpdate, user_id: str = CurrentUserId):
    return await service.update_subscription(subscription_id, user_id, payload)


@router.delete("/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subscription(subscription_id: str, user_id: str = CurrentUserId):
    await service.delete_subscription(subscription_id, user_id)
