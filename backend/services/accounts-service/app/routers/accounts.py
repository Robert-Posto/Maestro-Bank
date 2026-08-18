"""Rute protejate (JWT) ale accounts-service, pentru core banking.

Extern (prin Gateway) acestea devin:
  GET  /api/accounts/me
  GET  /api/accounts/me/cards
  GET  /api/accounts/{account_id}
  POST /api/accounts/dev/fund

Toate necesită un JWT valid — vezi app/security.py și
backend/gateway/app/routers/proxy.py (regula `_is_protected`).
"""

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, status

from app.database import get_database
from app.money import format_minor_amount
from app.models import AccountPublicOut, CardOut, DevFundRequest
from app.security import CurrentUserId

router = APIRouter(tags=["accounts"])


async def _get_account_for_user(user_id: str) -> dict:
    db = get_database()
    account = await db.accounts.find_one({"user_id": user_id})
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nu există niciun cont pentru acest utilizator.",
        )
    return account


def _to_public_account(account: dict) -> AccountPublicOut:
    return AccountPublicOut(
        id=str(account["_id"]),
        iban=account["iban"],
        currency=account["currency"],
        balance_minor=account["balance_minor"],
        balance=format_minor_amount(account["balance_minor"]),
        status=account["status"],
    )


@router.get("/me", response_model=AccountPublicOut)
async def get_my_account(user_id: str = CurrentUserId):
    account = await _get_account_for_user(user_id)
    return _to_public_account(account)


@router.get("/me/cards", response_model=list[CardOut], response_model_by_alias=False)
async def get_my_cards(user_id: str = CurrentUserId):
    db = get_database()
    cards = await db.cards.find({"user_id": user_id}).to_list(length=20)
    return cards


@router.post("/dev/fund", response_model=AccountPublicOut)
async def dev_fund_account(payload: DevFundRequest, user_id: str = CurrentUserId):
    """⚠️ STRICT DEVELOPMENT-ONLY.

    Adaugă fonduri FICTIVE contului userului autentificat, ca să putem
    testa transferuri fără nicio integrare bancară reală. NU este
    depunere/top-up real și nu trebuie confundat cu așa ceva.
    """
    db = get_database()
    account = await _get_account_for_user(user_id)

    await db.accounts.update_one(
        {"_id": account["_id"]},
        {"$inc": {"balance_minor": payload.amount_minor}},
    )
    updated = await db.accounts.find_one({"_id": account["_id"]})
    return _to_public_account(updated)


@router.get("/{account_id}", response_model=AccountPublicOut)
async def get_account_by_id(account_id: str, user_id: str = CurrentUserId):
    db = get_database()
    try:
        object_id = ObjectId(account_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID de cont invalid.") from exc

    account = await db.accounts.find_one({"_id": object_id})
    # Cont inexistent SAU aparținând altui user -> același 404, ca să nu
    # dezvăluim că un cont există dar nu-i aparține celui care întreabă.
    if account is None or account["user_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contul nu există.")

    return _to_public_account(account)
