"""Logica de business a points-service.

Separată de routing (app/routers/*.py) și modele (app/models.py). Acest
modul e singurul care atinge db.ledger_entries direct.

Soldul de puncte NU e un contor cache-uit — e SUMA (agregare Mongo) tuturor
intrărilor din ledger pentru un user (earn/redeem/wager/wheel_win). Fiecare
mutație e oricum necesară pentru istoricul din UI ("Istoric puncte") — deci
ledger-ul E acel istoric, fără o colecție separată și fără riscul ca un
contor cache-uit să iasă din sincron cu istoricul lui. Niciun sold nu poate
merge negativ — verificare "sold >= cost" ÎNAINTE de scriere, aceeași
fereastră de risc deja acceptată la transferuri/exchange (fără tranzacții
Mongo multi-document, doc deja existent în acest backend).

points-service NU citește niciodată direct accounts_db — orice credit REAL
de RON trece prin API-ul intern al accounts-service (exact aceleași
primitive deja construite și reutilizate de deposits-service/investments-service).
"""

import logging
import random
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import HTTPException, status

from app.config import settings
from app.database import get_database
from app.earn_rates import compute_points_earned, list_earn_rates
from app.models import (
    BalanceOut,
    ClaimWelcomeBonusOut,
    CreditForTransactionOut,
    LedgerEntryOut,
    RedeemRewardOut,
    RewardOut,
    WelcomeBonusStatusOut,
    WheelSegmentOut,
    WheelSpinOut,
)
from app.i18n import localized, translate
from app.rewards_catalog import REWARDS_CATALOG, get_reward
from app.welcome_bonus import WELCOME_BONUS_POINTS
from app.wheel_segments import REFERENCE_WAGER, WHEEL_SEGMENTS

logger = logging.getLogger("points-service")


async def _get_current_account(user_id: str) -> dict:
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.get(
                f"{settings.accounts_service_url}/internal/accounts/by-user-and-type/{user_id}/current"
            )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail=translate("accountsServiceUnavailable")
            ) from exc
    if response.status_code == 404:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=translate("currentAccountNotFound"))
    if response.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=translate("accountsServiceQueryError"))
    return response.json()


async def _notify_user(
    user_id: str, kind: str, message_key: str, message_params: dict | None = None, reference_id: str | None = None
) -> None:
    """Trimite o notificare persistentă către support-service. Best-effort —
    NU blochează și NU eșuează operația principală dacă support-service e
    indisponibil, la fel ca _notify_user din transactions-service.

    Trimite `message_key` + `message_params` (valori BRUTE) — support-service
    randează textul în limba CITITORULUI la fiecare citire (vezi
    support-service/app/i18n.py::render_notification), deci notificarea își
    schimbă limba la comutarea comutatorului, retroactiv."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post(
                f"{settings.support_service_url}/internal/notifications",
                json={
                    "user_id": user_id,
                    "kind": kind,
                    "message_key": message_key,
                    "message_params": message_params or {},
                    "reference_id": reference_id,
                },
            )
    except httpx.HTTPError:
        logger.warning("points-service: notificare eșuată (user_id=%s, kind=%s)", user_id, kind)


async def _credit_account(account_id: str, amount_minor: int) -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.post(
                f"{settings.accounts_service_url}/internal/accounts/{account_id}/credit",
                json={"amount_minor": amount_minor},
            )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail=translate("accountsServiceUnavailable")
            ) from exc
    if response.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=translate("accountCreditError"))


async def _balance(user_id: str) -> int:
    db = get_database()
    pipeline = [{"$match": {"user_id": user_id}}, {"$group": {"_id": None, "total": {"$sum": "$points_delta"}}}]
    result = await db.ledger_entries.aggregate(pipeline).to_list(length=1)
    return result[0]["total"] if result else 0


async def get_balance(user_id: str) -> BalanceOut:
    return BalanceOut(balance=await _balance(user_id))


async def _insert_entry(
    *,
    user_id: str,
    entry_type: str,
    points_delta: int,
    category: str | None = None,
    source_transaction_id: str | None = None,
    reward_id: str | None = None,
    spin_id: str | None = None,
    ron_credited_minor: int | None = None,
) -> dict:
    doc = {
        "user_id": user_id,
        "entry_type": entry_type,
        "points_delta": points_delta,
        "created_at": datetime.now(timezone.utc),
        "category": category,
        "source_transaction_id": source_transaction_id,
        "reward_id": reward_id,
        "spin_id": spin_id,
        "ron_credited_minor": ron_credited_minor,
    }
    result = await get_database().ledger_entries.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


def _to_ledger_entry_out(doc: dict) -> LedgerEntryOut:
    return LedgerEntryOut(
        id=str(doc["_id"]),
        entry_type=doc["entry_type"],
        points_delta=doc["points_delta"],
        created_at=doc["created_at"],
        category=doc.get("category"),
        reward_id=doc.get("reward_id"),
        spin_id=doc.get("spin_id"),
        ron_credited_minor=doc.get("ron_credited_minor"),
    )


async def list_history(user_id: str, limit: int, skip: int) -> list[LedgerEntryOut]:
    cursor = get_database().ledger_entries.find({"user_id": user_id}).sort("created_at", -1).skip(skip).limit(limit)
    docs = await cursor.to_list(length=limit)
    return [_to_ledger_entry_out(doc) for doc in docs]


def get_earn_rates() -> list[dict]:
    return list_earn_rates()


async def credit_for_transaction(
    user_id: str, category: str, amount_minor: int, is_merchant_payment: bool
) -> CreditForTransactionOut:
    """Apelat DOAR de transactions-service (vezi app/routers/internal.py),
    best-effort din partea lui — un transfer NU eșuează niciodată din cauza
    unei probleme aici. NU dă puncte pentru transferuri către alt user
    MaestroBank real (is_merchant_payment=False), indiferent de categorie."""
    if not is_merchant_payment:
        return CreditForTransactionOut(points_earned=0)

    points = compute_points_earned(category, amount_minor)
    if points <= 0:
        return CreditForTransactionOut(points_earned=0)

    await _insert_entry(user_id=user_id, entry_type="earn", points_delta=points, category=category)
    logger.info("points-service: %s puncte câștigate (user_id=%s, categorie=%s)", points, user_id, category)
    return CreditForTransactionOut(points_earned=points)


async def _has_claimed_welcome_bonus(user_id: str) -> bool:
    doc = await get_database().ledger_entries.find_one({"user_id": user_id, "entry_type": "welcome_bonus"})
    return doc is not None


async def get_welcome_bonus_status(user_id: str) -> WelcomeBonusStatusOut:
    claimed = await _has_claimed_welcome_bonus(user_id)
    return WelcomeBonusStatusOut(claimed=claimed, bonus_points=WELCOME_BONUS_POINTS)


async def claim_welcome_bonus(user_id: str) -> ClaimWelcomeBonusOut:
    """Un singur bonus per user — a doua încercare e respinsă (409), nu
    acordă din nou. Verificarea + scrierea nu sunt atomice (fără tranzacții
    Mongo multi-document, aceeași fereastră de risc deja acceptată în tot
    acest backend) — un dublu-click chiar simultan ar putea, teoretic,
    trece de ambele verificări; impactul practic e neglijabil (un bonus fix,
    mic, o singură dată în viața contului), nu justifică o soluție mai
    complexă."""
    if await _has_claimed_welcome_bonus(user_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=translate("welcomeBonusAlreadyClaimed"))

    await _insert_entry(user_id=user_id, entry_type="welcome_bonus", points_delta=WELCOME_BONUS_POINTS)
    new_balance = await _balance(user_id)
    logger.info("points-service: bonus de bun-venit revendicat (user_id=%s, puncte=%s)", user_id, WELCOME_BONUS_POINTS)
    await _notify_user(
        user_id,
        "welcome_bonus_claimed",
        "welcomeBonus",
        {"points": WELCOME_BONUS_POINTS},
    )
    return ClaimWelcomeBonusOut(new_balance=new_balance, points_awarded=WELCOME_BONUS_POINTS)


async def list_rewards(user_id: str) -> list[RewardOut]:
    balance = await _balance(user_id)
    return [
        RewardOut(
            id=reward["id"],
            title=localized(reward, "title"),
            description=localized(reward, "description"),
            cost_points=reward["cost_points"],
            reward_value_minor=reward["reward_value_minor"],
            affordable=balance >= reward["cost_points"],
        )
        for reward in REWARDS_CATALOG
    ]


async def redeem_reward(user_id: str, reward_id: str) -> RedeemRewardOut:
    reward = get_reward(reward_id)
    if reward is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=translate("rewardNotFound"))

    balance = await _balance(user_id)
    if balance < reward["cost_points"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=translate("notEnoughPointsForReward")
        )

    account = await _get_current_account(user_id)
    await _credit_account(account["id"], reward["reward_value_minor"])
    await _insert_entry(
        user_id=user_id,
        entry_type="redeem",
        points_delta=-reward["cost_points"],
        reward_id=reward_id,
        ron_credited_minor=reward["reward_value_minor"],
    )
    new_balance = await _balance(user_id)
    logger.info(
        "points-service: recompensă răscumpărată (user_id=%s, reward_id=%s, ron_minor=%s)",
        user_id,
        reward_id,
        reward["reward_value_minor"],
    )
    await _notify_user(
        user_id,
        "reward_redeemed",
        "rewardRedeemed",
        {
            "title_ro": reward["title"],
            "title_en": reward.get("title_en", reward["title"]),
            "amount_minor": reward["reward_value_minor"],
        },
    )
    return RedeemRewardOut(
        new_balance=new_balance, ron_credited_minor=reward["reward_value_minor"], account_id=account["id"]
    )


def list_wheel_segments() -> list[WheelSegmentOut]:
    return [
        WheelSegmentOut(id=s["id"], label=localized(s, "label"), reward_value_minor=s.get("reward_value_minor"))
        for s in WHEEL_SEGMENTS
    ]


def _pick_weighted_segment(wagered_points: int) -> dict:
    """Formulă simplă, documentată — interpolare liniară a greutății
    fiecărui segment între weight_base (pariu 0) și weight_boosted (pariu
    >= REFERENCE_WAGER), apoi o alegere ponderată aleatorie standard
    (random.choices). NU e nevoie de un generator criptografic aici — e o
    roată de premii de demo, nu un secret JWT."""
    t = min(wagered_points / REFERENCE_WAGER, 1.0)
    weights = [s["weight_base"] + t * (s["weight_boosted"] - s["weight_base"]) for s in WHEEL_SEGMENTS]
    return random.choices(WHEEL_SEGMENTS, weights=weights, k=1)[0]


async def spin_wheel(user_id: str, wagered_points: int) -> WheelSpinOut:
    balance = await _balance(user_id)
    if wagered_points > balance:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=translate("notEnoughPointsForWager"))

    spin_id = str(uuid.uuid4())
    # Pariul se scade IMEDIAT, indiferent de rezultat — e costul biletului,
    # nu o "miză recuperabilă".
    await _insert_entry(user_id=user_id, entry_type="wager", points_delta=-wagered_points, spin_id=spin_id)

    # Rezultatul e decis AICI, integral pe server, ÎNAINTE de orice răspuns
    # către client — frontend-ul primește deja câștigătorul decis și DOAR
    # animă roata să se oprească pe el (vezi design-ul, secțiunea de
    # securitate: clientul nu calculează și nu influențează niciodată
    # rezultatul).
    winning_segment = _pick_weighted_segment(wagered_points)
    ron_credited_minor: int | None = None

    if winning_segment.get("reward_value_minor"):
        account = await _get_current_account(user_id)
        ron_credited_minor = winning_segment["reward_value_minor"]
        await _credit_account(account["id"], ron_credited_minor)
        await _insert_entry(
            user_id=user_id,
            entry_type="wheel_win",
            points_delta=0,
            spin_id=spin_id,
            ron_credited_minor=ron_credited_minor,
        )
        await _notify_user(
            user_id,
            "raffle_win",
            "wheelWin",
            {"amount_minor": ron_credited_minor},
            reference_id=spin_id,
        )

    new_balance = await _balance(user_id)
    logger.info(
        "points-service: spin roată (user_id=%s, pariu=%s, segment=%s, ron_minor=%s)",
        user_id,
        wagered_points,
        winning_segment["id"],
        ron_credited_minor,
    )
    return WheelSpinOut(
        winning_segment_id=winning_segment["id"],
        winning_label=localized(winning_segment, "label"),
        new_balance=new_balance,
        ron_credited_minor=ron_credited_minor,
        spin_id=spin_id,
    )
