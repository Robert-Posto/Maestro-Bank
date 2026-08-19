"""Logica de business a accounts-service.

Separată de routing (`app/routers/accounts.py` pentru rutele protejate
JWT, `app/routers/internal.py` pentru rutele service-to-service) și de
modele (`app/models.py`). Acest modul e singurul care atinge
`db.accounts` / `db.cards` direct.
"""

import logging
import random
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status

from app.database import get_database
from app.iban_service import generate_unique_demo_iban
from app.money import format_minor_amount
from app.models import (
    AccountPublicOut,
    BeneficiaryCreate,
    CardLimitUpdate,
    CardSettingsUpdate,
    InternalAccountView,
    InternalTransferResponse,
)

logger = logging.getLogger("accounts-service")

_DEMO_CARD_TYPE = "virtual"
_DEMO_CARD_VALID_YEARS = 3


# --- helpers de conversie (DB -> DTO) -------------------------------------


def to_public_account(account: dict) -> AccountPublicOut:
    return AccountPublicOut(
        id=str(account["_id"]),
        iban=account["iban"],
        currency=account["currency"],
        balance_minor=account["balance_minor"],
        balance=format_minor_amount(account["balance_minor"]),
        status=account["status"],
        created_at=account["created_at"],
    )


def _to_internal_view(account: dict) -> InternalAccountView:
    return InternalAccountView(
        id=str(account["_id"]),
        user_id=account["user_id"],
        iban=account["iban"],
        currency=account["currency"],
        balance_minor=account["balance_minor"],
        status=account["status"],
    )


def _generate_demo_last_four() -> str:
    return f"{random.randint(0, 9999):04d}"


def _demo_expiry() -> tuple[int, int]:
    now = datetime.now(timezone.utc)
    return now.month, now.year + _DEMO_CARD_VALID_YEARS


# --- rute protejate JWT (app/routers/accounts.py) -------------------------


async def get_account_for_user(user_id: str) -> dict:
    db = get_database()
    account = await db.accounts.find_one({"user_id": user_id})
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nu există niciun cont pentru acest utilizator.",
        )
    return account


async def get_cards_for_user(user_id: str) -> list[dict]:
    db = get_database()
    return await db.cards.find({"user_id": user_id}).to_list(length=20)


async def _get_card_for_user(card_id: str, user_id: str) -> dict:
    """Rezolvă un card DOAR dacă aparține userului autentificat.

    Identitatea vine STRICT din JWT (`user_id`, injectat de router prin
    `CurrentUserId`) — niciodată dintr-un parametru trimis de frontend.
    Card inexistent SAU aparținând altui user -> același 404, ca să nu
    dezvăluim că un card există dar nu-i aparține celui care întreabă.
    """
    db = get_database()
    try:
        object_id = ObjectId(card_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID de card invalid.") from exc

    card = await db.cards.find_one({"_id": object_id})
    if card is None or card["user_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cardul nu există.")
    return card


async def _set_card_frozen(card_id: str, user_id: str, is_frozen: bool) -> dict:
    db = get_database()
    card = await _get_card_for_user(card_id, user_id)
    await db.cards.update_one({"_id": card["_id"]}, {"$set": {"is_frozen": is_frozen}})
    logger.info("accounts-service: card %s (user_id=%s) -> is_frozen=%s", card["_id"], user_id, is_frozen)
    return await db.cards.find_one({"_id": card["_id"]})


async def freeze_card(card_id: str, user_id: str) -> dict:
    return await _set_card_frozen(card_id, user_id, True)


async def unfreeze_card(card_id: str, user_id: str) -> dict:
    return await _set_card_frozen(card_id, user_id, False)


async def update_card_settings(card_id: str, user_id: str, payload: CardSettingsUpdate) -> dict:
    db = get_database()
    card = await _get_card_for_user(card_id, user_id)

    updates = {key: value for key, value in payload.model_dump(exclude_unset=True).items() if value is not None}
    if updates:
        await db.cards.update_one({"_id": card["_id"]}, {"$set": updates})
        logger.info("accounts-service: card %s (user_id=%s) settings actualizate: %s", card["_id"], user_id, updates)

    return await db.cards.find_one({"_id": card["_id"]})


async def update_card_limit(card_id: str, user_id: str, payload: CardLimitUpdate) -> dict:
    db = get_database()
    card = await _get_card_for_user(card_id, user_id)

    await db.cards.update_one({"_id": card["_id"]}, {"$set": {"daily_limit_minor": payload.daily_limit_minor}})
    logger.info(
        "accounts-service: card %s (user_id=%s) daily_limit_minor=%s",
        card["_id"],
        user_id,
        payload.daily_limit_minor,
    )
    return await db.cards.find_one({"_id": card["_id"]})


# --- Beneficiari (transfer către IBAN salvat) -----------------------------


async def create_beneficiary(user_id: str, payload: BeneficiaryCreate) -> dict:
    db = get_database()
    doc = {
        "user_id": user_id,
        "name": payload.name,
        "iban": payload.iban,
        "created_at": datetime.now(timezone.utc),
    }
    result = await db.beneficiaries.insert_one(doc)
    return await db.beneficiaries.find_one({"_id": result.inserted_id})


async def get_beneficiaries_for_user(user_id: str) -> list[dict]:
    db = get_database()
    cursor = db.beneficiaries.find({"user_id": user_id}).sort("created_at", -1)
    return await cursor.to_list(length=100)


async def delete_beneficiary(beneficiary_id: str, user_id: str) -> None:
    db = get_database()
    try:
        object_id = ObjectId(beneficiary_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID de beneficiar invalid.") from exc

    result = await db.beneficiaries.delete_one({"_id": object_id, "user_id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Beneficiarul nu există.")


async def add_demo_funds(user_id: str, amount_minor: int) -> AccountPublicOut:
    """⚠️ STRICT DEVELOPMENT-ONLY.

    Adaugă fonduri FICTIVE contului userului autentificat, ca să putem
    testa transferuri fără nicio integrare bancară reală. NU este
    depunere/top-up real și nu trebuie confundat cu așa ceva.
    """
    db = get_database()
    account = await get_account_for_user(user_id)

    await db.accounts.update_one(
        {"_id": account["_id"]},
        {"$inc": {"balance_minor": amount_minor}},
    )
    updated = await db.accounts.find_one({"_id": account["_id"]})
    return to_public_account(updated)


async def get_account_by_id_for_user(account_id: str, user_id: str) -> AccountPublicOut:
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

    return to_public_account(account)


# --- rute interne, service-to-service (app/routers/internal.py) -----------


async def provision_account(user_id: str) -> tuple[dict, dict]:
    """Creează automat 1 cont curent RON (balance_minor=0) + 1 card virtual demo.

    Apelat de auth-service imediat după `POST /auth/register`.
    """
    db = get_database()

    existing_account = await db.accounts.find_one({"user_id": user_id})
    if existing_account is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Userul are deja un cont provizionat.")

    iban = await generate_unique_demo_iban(db)
    now = datetime.now(timezone.utc)

    account_doc = {
        "user_id": user_id,
        "iban": iban,
        "currency": "RON",
        "balance_minor": 0,
        "status": "active",
        "created_at": now,
    }
    account_result = await db.accounts.insert_one(account_doc)

    expiry_month, expiry_year = _demo_expiry()
    card_doc = {
        "user_id": user_id,
        "account_id": account_result.inserted_id,
        "last_four": _generate_demo_last_four(),
        "expiry_month": expiry_month,
        "expiry_year": expiry_year,
        "status": "active",
        "type": _DEMO_CARD_TYPE,
        "created_at": now,
        # Card controls (Cardul meu) — valori implicite explicite la creare.
        "is_frozen": False,
        "online_payments_enabled": True,
        "contactless_enabled": True,
        "atm_withdrawals_enabled": True,
        "international_payments_enabled": True,
        "daily_limit_minor": 500_000,
    }
    card_result = await db.cards.insert_one(card_doc)

    logger.info(
        "accounts-service: cont provizionat (user_id=%s, account_id=%s, iban=%s, card_id=%s)",
        user_id,
        account_result.inserted_id,
        iban,
        card_result.inserted_id,
    )

    account = await db.accounts.find_one({"_id": account_result.inserted_id})
    card = await db.cards.find_one({"_id": card_result.inserted_id})
    return account, card


async def get_account_by_user(user_id: str) -> InternalAccountView:
    """Folosit de transactions-service pentru a determina contul SURSĂ al userului autentificat."""
    db = get_database()
    account = await db.accounts.find_one({"user_id": user_id})
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nu există cont pentru acest user_id.")
    return _to_internal_view(account)


async def get_account_by_iban(iban: str) -> InternalAccountView:
    """Folosit de transactions-service pentru a rezolva IBAN-ul destinație la un cont."""
    db = get_database()
    account = await db.accounts.find_one({"iban": iban.strip().upper()})
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nu există niciun cont cu acest IBAN.")
    return _to_internal_view(account)


async def apply_internal_transfer(from_account_id: str, to_account_id: str, amount_minor: int) -> InternalTransferResponse:
    """Aplică efectiv mișcarea de sold (debit + credit).

    Apelat DOAR de transactions-service, DUPĂ ce a validat deja transferul
    (sold suficient, conturi active etc. — vezi transactions-service).

    NOTĂ despre atomicitate: MongoDB standalone (fără replica set), cum
    rulează în acest mediu de development, NU suportă tranzacții
    multi-document. NU am complicat infrastructura (nu am introdus un
    replica set) doar pentru acest milestone. În schimb:
      1. debit-ul e o operație CONDIȚIONATĂ, atomică la nivel de document
         (`update_one` cu filtru `balance_minor >= amount_minor` — dacă
         soldul nu (mai) e suficient în momentul exact al operației,
         update-ul pur și simplu nu se aplică, fără race condition de
         tip citește-apoi-scrie);
      2. credit-ul se aplică doar dacă debit-ul a reușit;
      3. dacă creditul eșuează (cont destinație dispărut/inactiv exact în
         acest interval), facem ROLLBACK MANUAL al debitului.
    Rămâne o fereastră teoretică (foarte îngustă) între debit și credit în
    care banii "nu există" nicăieri dacă procesul ar crăpa exact atunci —
    într-un sistem bancar REAL ar fi nevoie de un ledger / mecanism de
    tranzacționare atomică mult mai strict (ex. double-entry ledger cu
    reconciliere, sau MongoDB replica set + sesiuni de tranzacție).
    Această implementare NU oferă garanții bancare reale — e un demo.
    """
    db = get_database()

    try:
        from_id = ObjectId(from_account_id)
        to_id = ObjectId(to_account_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID de cont invalid.") from exc

    debit_result = await db.accounts.update_one(
        {"_id": from_id, "status": "active", "balance_minor": {"$gte": amount_minor}},
        {"$inc": {"balance_minor": -amount_minor}},
    )
    if debit_result.modified_count != 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Sold insuficient sau cont sursă inactiv/inexistent.",
        )

    credit_result = await db.accounts.update_one(
        {"_id": to_id, "status": "active"},
        {"$inc": {"balance_minor": amount_minor}},
    )
    if credit_result.modified_count != 1:
        # Rollback manual — creditul a eșuat, restituim suma la sursă.
        await db.accounts.update_one({"_id": from_id}, {"$inc": {"balance_minor": amount_minor}})
        logger.error(
            "accounts-service: credit eșuat, rollback aplicat (from=%s, to=%s, amount_minor=%s)",
            from_id,
            to_id,
            amount_minor,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cont destinație inactiv sau inexistent — transfer anulat.",
        )

    from_account = await db.accounts.find_one({"_id": from_id})
    to_account = await db.accounts.find_one({"_id": to_id})

    logger.info(
        "accounts-service: transfer aplicat (from=%s, to=%s, amount_minor=%s)",
        from_id,
        to_id,
        amount_minor,
    )

    return InternalTransferResponse(
        from_balance_minor=from_account["balance_minor"],
        to_balance_minor=to_account["balance_minor"],
    )
