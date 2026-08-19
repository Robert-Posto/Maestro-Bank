"""Rute protejate (JWT) pentru controlul cardurilor (Cardul meu).

Doar validare (Pydantic/JWT via `CurrentUserId`) și delegare către
app/service.py — logica de business trăiește acolo. Userul poate
modifica DOAR cardurile lui — identitatea vine din JWT, niciodată dintr-un
user_id trimis de frontend.

Extern (prin Gateway) acestea devin:
  POST  /api/accounts/cards
  POST  /api/accounts/cards/{card_id}/reveal
  PATCH /api/accounts/cards/{card_id}/freeze
  PATCH /api/accounts/cards/{card_id}/unfreeze
  PATCH /api/accounts/cards/{card_id}/settings
  PATCH /api/accounts/cards/{card_id}/limits

NOTĂ: prefixul "/cards" e un router SEPARAT de accounts_router (care are
GET /{account_id} la rădăcină) tocmai ca să nu existe nicio ambiguitate
de rutare între cele două.
"""

from fastapi import APIRouter, status

from app import service
from app.models import CardCreateRequest, CardLimitUpdate, CardOut, CardRevealOut, CardRevealRequest, CardSettingsUpdate
from app.security import CurrentUserId

router = APIRouter(prefix="/cards", tags=["cards"])


@router.post("", response_model=CardOut, response_model_by_alias=False, status_code=status.HTTP_201_CREATED)
async def create_card(payload: CardCreateRequest, user_id: str = CurrentUserId):
    return await service.create_card(user_id, payload)


@router.post("/{card_id}/reveal", response_model=CardRevealOut)
async def reveal_card(card_id: str, payload: CardRevealRequest, user_id: str = CurrentUserId):
    return await service.reveal_card(card_id, user_id, payload.password)


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
