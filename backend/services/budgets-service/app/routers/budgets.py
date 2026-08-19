"""Rute protejate (JWT) pentru bugete.

Extern (prin Gateway) acestea devin:
  POST   /api/budgets/budgets
  GET    /api/budgets/budgets
  PATCH  /api/budgets/budgets/{id}
  DELETE /api/budgets/budgets/{id}

Bugetul e INFORMATIV — nu blochează transferuri (transactions-service nu
citește niciodată budgets_db). "spent"/"remaining"/"progres %" se
calculează în frontend, combinând acest răspuns cu
GET /api/transactions/analytics/spending (pe categorie).
"""

from fastapi import APIRouter, status

from app import service
from app.models import BudgetCreate, BudgetOut, BudgetUpdate
from app.security import CurrentUserId

router = APIRouter(prefix="/budgets", tags=["budgets"])


@router.post("", response_model=BudgetOut, response_model_by_alias=False, status_code=status.HTTP_201_CREATED)
async def create_budget(payload: BudgetCreate, user_id: str = CurrentUserId):
    return await service.create_budget(user_id, payload)


@router.get("", response_model=list[BudgetOut], response_model_by_alias=False)
async def list_budgets(user_id: str = CurrentUserId):
    return await service.list_budgets_for_user(user_id)


@router.patch("/{budget_id}", response_model=BudgetOut, response_model_by_alias=False)
async def update_budget(budget_id: str, payload: BudgetUpdate, user_id: str = CurrentUserId):
    return await service.update_budget(budget_id, user_id, payload)


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget(budget_id: str, user_id: str = CurrentUserId):
    await service.delete_budget(budget_id, user_id)
