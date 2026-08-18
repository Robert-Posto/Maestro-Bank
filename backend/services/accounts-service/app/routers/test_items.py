"""Endpoint-uri TEMPORARE de dezvoltare pentru accounts-service.

Scopul lor este exclusiv să demonstreze fluxul end-to-end:
Angular -> Nginx -> Gateway -> accounts-service -> accounts_db.

NU fac parte din logica bancară finală (conturi, IBAN, solduri, carduri)
și vor fi înlocuite/eliminate când se implementează accounts/cards reale.

Extern (prin Gateway) acestea devin: /api/accounts/test-items.
"""

from fastapi import APIRouter

from app.database import get_database
from app.models import TestItemCreate, TestItemOut

router = APIRouter(tags=["dev-test"])


@router.post(
    "/test-items",
    response_model=TestItemOut,
    response_model_by_alias=False,
    status_code=201,
)
async def create_test_item(item: TestItemCreate):
    db = get_database()
    result = await db.test_items.insert_one(item.model_dump())
    created = await db.test_items.find_one({"_id": result.inserted_id})
    return created


@router.get("/test-items", response_model=list[TestItemOut], response_model_by_alias=False)
async def list_test_items():
    db = get_database()
    items = await db.test_items.find().to_list(length=100)
    return items
