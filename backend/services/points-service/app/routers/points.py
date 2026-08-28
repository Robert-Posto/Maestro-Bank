"""Rute protejate (JWT) ale points-service.

Doar validare și delegare către app/service.py — logica de business
trăiește acolo.

Extern (prin Gateway) acestea devin:
  GET  /api/points/balance
  GET  /api/points/history
  GET  /api/points/earn-rates
  GET  /api/points/rewards
  POST /api/points/rewards/{id}/redeem
  GET  /api/points/wheel/segments
  POST /api/points/wheel/spin
  GET  /api/points/welcome-bonus/status
  POST /api/points/welcome-bonus/claim
"""

from fastapi import APIRouter, Query

from app import service
from app.models import (
    BalanceOut,
    ClaimWelcomeBonusOut,
    EarnRateOut,
    LedgerEntryOut,
    RedeemRewardOut,
    RewardOut,
    WelcomeBonusStatusOut,
    WheelSegmentOut,
    WheelSpinOut,
    WheelSpinRequest,
)
from app.security import CurrentUserId

router = APIRouter(prefix="/points", tags=["points"])


@router.get("/balance", response_model=BalanceOut)
async def get_balance(user_id: str = CurrentUserId):
    return await service.get_balance(user_id)


@router.get("/history", response_model=list[LedgerEntryOut])
async def get_history(
    limit: int = Query(default=50, ge=1, le=200), skip: int = Query(default=0, ge=0), user_id: str = CurrentUserId
):
    return await service.list_history(user_id, limit, skip)


@router.get("/earn-rates", response_model=list[EarnRateOut])
async def get_earn_rates(user_id: str = CurrentUserId):
    return service.get_earn_rates()


@router.get("/rewards", response_model=list[RewardOut])
async def get_rewards(user_id: str = CurrentUserId):
    return await service.list_rewards(user_id)


@router.post("/rewards/{reward_id}/redeem", response_model=RedeemRewardOut)
async def redeem_reward_route(reward_id: str, user_id: str = CurrentUserId):
    return await service.redeem_reward(user_id, reward_id)


@router.get("/wheel/segments", response_model=list[WheelSegmentOut])
async def get_wheel_segments(user_id: str = CurrentUserId):
    return service.list_wheel_segments()


@router.post("/wheel/spin", response_model=WheelSpinOut)
async def spin_wheel_route(payload: WheelSpinRequest, user_id: str = CurrentUserId):
    return await service.spin_wheel(user_id, payload.wagered_points)


@router.get("/welcome-bonus/status", response_model=WelcomeBonusStatusOut)
async def get_welcome_bonus_status(user_id: str = CurrentUserId):
    return await service.get_welcome_bonus_status(user_id)


@router.post("/welcome-bonus/claim", response_model=ClaimWelcomeBonusOut)
async def claim_welcome_bonus_route(user_id: str = CurrentUserId):
    return await service.claim_welcome_bonus(user_id)
