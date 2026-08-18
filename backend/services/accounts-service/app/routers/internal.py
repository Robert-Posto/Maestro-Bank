"""Endpoint-uri INTERNE ale accounts-service.

Apelabile DOAR container-to-container (de auth-service și
transactions-service), folosind adresa internă Docker
`http://accounts-service:8000`. NU sunt expuse prin API Gateway —
gateway blochează explicit orice path care începe cu "internal/" (vezi
backend/gateway/app/routers/proxy.py), tocmai ca aceste rute să nu poată
fi apelate din browser/Angular.
"""

import logging
import random
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, status

from app.database import get_database
from app.iban_service import generate_unique_demo_iban
from app.models import (
    InternalAccountView,
    InternalTransferRequest,
    InternalTransferResponse,
    ProvisionRequest,
    ProvisionResponse,
)

logger = logging.getLogger("accounts-service")

router = APIRouter(prefix="/internal/accounts", tags=["internal"])

_DEMO_CARD_TYPE = "virtual"
_DEMO_CARD_VALID_YEARS = 3


def _generate_demo_last_four() -> str:
    return f"{random.randint(0, 9999):04d}"


def _demo_expiry() -> tuple[int, int]:
    now = datetime.now(timezone.utc)
    return now.month, now.year + _DEMO_CARD_VALID_YEARS


def _to_internal_view(account: dict) -> InternalAccountView:
    return InternalAccountView(
        id=str(account["_id"]),
        user_id=account["user_id"],
        iban=account["iban"],
        currency=account["currency"],
        balance_minor=account["balance_minor"],
        status=account["status"],
    )


@router.post("/provision", response_model=ProvisionResponse, status_code=status.HTTP_201_CREATED)
async def provision_account(payload: ProvisionRequest):
    """Creează automat 1 cont curent RON (balance_minor=0) + 1 card virtual demo.

    Apelat de auth-service imediat după `POST /auth/register`.
    """
    db = get_database()

    existing_account = await db.accounts.find_one({"user_id": payload.user_id})
    if existing_account is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Userul are deja un cont provizionat.")

    iban = await generate_unique_demo_iban(db)
    now = datetime.now(timezone.utc)

    account_doc = {
        "user_id": payload.user_id,
        "iban": iban,
        "currency": "RON",
        "balance_minor": 0,
        "status": "active",
        "created_at": now,
    }
    account_result = await db.accounts.insert_one(account_doc)

    expiry_month, expiry_year = _demo_expiry()
    card_doc = {
        "user_id": payload.user_id,
        "account_id": account_result.inserted_id,
        "last_four": _generate_demo_last_four(),
        "expiry_month": expiry_month,
        "expiry_year": expiry_year,
        "status": "active",
        "type": _DEMO_CARD_TYPE,
        "created_at": now,
    }
    card_result = await db.cards.insert_one(card_doc)

    logger.info(
        "accounts-service: cont provizionat (user_id=%s, account_id=%s, iban=%s, card_id=%s)",
        payload.user_id,
        account_result.inserted_id,
        iban,
        card_result.inserted_id,
    )

    account = await db.accounts.find_one({"_id": account_result.inserted_id})
    card = await db.cards.find_one({"_id": card_result.inserted_id})
    return ProvisionResponse(account=account, card=card)


@router.get("/by-user/{user_id}", response_model=InternalAccountView)
async def get_account_by_user(user_id: str):
    """Folosit de transactions-service pentru a determina contul SURSĂ al userului autentificat."""
    db = get_database()
    account = await db.accounts.find_one({"user_id": user_id})
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nu există cont pentru acest user_id.")
    return _to_internal_view(account)


@router.get("/by-iban/{iban}", response_model=InternalAccountView)
async def get_account_by_iban(iban: str):
    """Folosit de transactions-service pentru a rezolva IBAN-ul destinație la un cont."""
    db = get_database()
    account = await db.accounts.find_one({"iban": iban.strip().upper()})
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nu există niciun cont cu acest IBAN.")
    return _to_internal_view(account)


@router.post("/transfer", response_model=InternalTransferResponse)
async def apply_internal_transfer(payload: InternalTransferRequest):
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
        from_id = ObjectId(payload.from_account_id)
        to_id = ObjectId(payload.to_account_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID de cont invalid.") from exc

    debit_result = await db.accounts.update_one(
        {"_id": from_id, "status": "active", "balance_minor": {"$gte": payload.amount_minor}},
        {"$inc": {"balance_minor": -payload.amount_minor}},
    )
    if debit_result.modified_count != 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Sold insuficient sau cont sursă inactiv/inexistent.",
        )

    credit_result = await db.accounts.update_one(
        {"_id": to_id, "status": "active"},
        {"$inc": {"balance_minor": payload.amount_minor}},
    )
    if credit_result.modified_count != 1:
        # Rollback manual — creditul a eșuat, restituim suma la sursă.
        await db.accounts.update_one({"_id": from_id}, {"$inc": {"balance_minor": payload.amount_minor}})
        logger.error(
            "accounts-service: credit eșuat, rollback aplicat (from=%s, to=%s, amount_minor=%s)",
            from_id,
            to_id,
            payload.amount_minor,
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
        payload.amount_minor,
    )

    return InternalTransferResponse(
        from_balance_minor=from_account["balance_minor"],
        to_balance_minor=to_account["balance_minor"],
    )
