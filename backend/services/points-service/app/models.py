"""DTO-uri (request/response) pentru points-service. Formele documentelor
Mongo trăiesc informal în app/service.py (fără schema Pydantic separată
pentru documente, la fel ca restul serviciilor din acest backend)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

LedgerEntryType = Literal["earn", "redeem", "wager", "wheel_win"]


class BalanceOut(BaseModel):
    balance: int


class LedgerEntryOut(BaseModel):
    id: str
    entry_type: LedgerEntryType
    points_delta: int
    created_at: datetime
    category: str | None = None
    reward_id: str | None = None
    spin_id: str | None = None
    ron_credited_minor: int | None = None


class EarnRateOut(BaseModel):
    category: str
    rate_percent: float


class RewardOut(BaseModel):
    id: str
    title: str
    description: str
    cost_points: int
    reward_value_minor: int
    affordable: bool


class RedeemRewardOut(BaseModel):
    new_balance: int
    ron_credited_minor: int
    account_id: str


class WheelSegmentOut(BaseModel):
    id: str
    label: str
    reward_value_minor: int | None = None


class WheelSpinRequest(BaseModel):
    wagered_points: int = Field(gt=0)


class WheelSpinOut(BaseModel):
    winning_segment_id: str
    winning_label: str
    new_balance: int
    ron_credited_minor: int | None = None
    spin_id: str


class CreditForTransactionRequest(BaseModel):
    """Trimis DOAR de transactions-service — payload-ul intern, vezi
    app/routers/internal.py. `is_merchant_payment` = `to_name is None` acolo
    (semnalul deja folosit în transactions-service pt "plată către un cont
    fără user MaestroBank real")."""

    user_id: str
    category: str
    amount_minor: int = Field(gt=0)
    is_merchant_payment: bool


class CreditForTransactionOut(BaseModel):
    points_earned: int
