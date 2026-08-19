"""Rute protejate (JWT) pentru controlul cardurilor (Cardul meu).

Doar validare (Pydantic/JWT via `CurrentUserId`) și delegare către
app/service.py — logica de business trăiește acolo. Userul poate
modifica DOAR cardurile lui — identitatea vine din JWT, niciodată dintr-un
user_id trimis de frontend.

Extern (prin Gateway) acestea devin:
  PATCH /api/accounts/cards/{card_id}/freeze
  PATCH /api/accounts/cards/{card_id}/unfreeze
  PATCH /api/accounts/cards/{card_id}/settings
  PATCH /api/accounts/cards/{card_id}/limits

NOTĂ: prefixul "/cards" e un router SEPARAT de accounts_router (care are
GET /{account_id} la rădăcină) tocmai ca să nu existe nicio ambiguitate
de rutare între cele două.
"""

from fastapi import APIRouter

from app import service
from app.models import CardLimitUpdate, CardOut, CardSettingsUpdate
from app.security import CurrentUserId

router = APIRouter(prefix="/cards", tags=["cards"])


@router.patch("/{card_id}/freeze", response_model=CardOut, response_model_by_alias=False)
async def freeze_card(card_id: str, user_id: str = CurrentUserId):
    return await service.freeze_card(card_id, user_id)


@router.patch("/{card_id}/unfreeze", response_model=CardOut, response_model_by_alias=False)
async def unfreeze_card(card_id: str, user_id: str = CurrentUserId):
    return await service.unfreeze_card(card_id, user_id)


@router.patch("/{card_id}/settings", response_model=CardOut, response_model_by_alias=False)
async def update_card_settings(card_id: str, payload: CardSettingsUpdate, user_id: str = CurrentUserId):
    return await service.update_card_settings(card_id, user_id, payload)


@router.patch("/{card_id}/limits", response_model=CardOut, response_model_by_alias=False)
async def update_card_limit(card_id: str, payload: CardLimitUpdate, user_id: str = CurrentUserId):
    return await service.update_card_limit(card_id, user_id, payload)
