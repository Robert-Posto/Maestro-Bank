"""Rute protejate (JWT) ale transactions-service.

Extern (prin Gateway) acestea devin:
  POST /api/transactions/transfers
  GET  /api/transactions
  GET  /api/transactions/{id}

Acest serviciu NU citește niciodată direct accounts_db — orice informație
despre conturi (sold, status, IBAN) vine prin API-ul accounts-service,
folosind adresa internă Docker (`http://accounts-service:8000`), NEVER
localhost. Vezi `_get_account_by_user` / `_get_account_by_iban` /
`_apply_transfer` mai jos.
"""

import logging
from datetime import datetime, timezone

import httpx
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, Query, status

from app.config import settings
from app.database import get_database
from app.money import format_minor_amount
from app.models import TransactionOut, TransferRequest
from app.security import CurrentUserId

logger = logging.getLogger("transactions-service")

router = APIRouter(prefix="/transactions", tags=["transactions"])


async def _get_account_by_user(user_id: str) -> dict:
    """Rezolvă contul SURSĂ al userului autentificat, prin accounts-service."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.get(f"{settings.accounts_service_url}/internal/accounts/by-user/{user_id}")
        except httpx.RequestError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="accounts-service indisponibil.") from exc

    if response.status_code == 404:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nu există un cont pentru utilizatorul curent.")
    if response.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Eroare la interogarea accounts-service.")
    return response.json()


async def _get_account_by_iban(iban: str) -> dict | None:
    """Rezolvă contul DESTINAȚIE după IBAN, prin accounts-service."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.get(f"{settings.accounts_service_url}/internal/accounts/by-iban/{iban}")
        except httpx.RequestError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="accounts-service indisponibil.") from exc

    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Eroare la interogarea accounts-service.")
    return response.json()


async def _apply_transfer(from_account_id: str, to_account_id: str, amount_minor: int) -> dict:
    """Cere accounts-service să aplice EFECTIV mutarea de sold (debit + credit)."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.post(
                f"{settings.accounts_service_url}/internal/accounts/transfer",
                json={
                    "from_account_id": from_account_id,
                    "to_account_id": to_account_id,
                    "amount_minor": amount_minor,
                },
            )
        except httpx.RequestError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="accounts-service indisponibil.") from exc

    if response.status_code == 409:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Sold insuficient sau cont inactiv.")
    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Eroare la aplicarea transferului în accounts-service.",
        )
    return response.json()


def _to_transaction_view(doc: dict, viewer_account_id: str) -> dict:
    is_outgoing = doc["from_account_id"] == viewer_account_id
    return {
        "_id": doc["_id"],
        "direction": "outgoing" if is_outgoing else "incoming",
        "amount_minor": doc["amount_minor"],
        "amount": format_minor_amount(doc["amount_minor"]),
        "currency": doc["currency"],
        "counterparty_iban": doc["to_iban"] if is_outgoing else doc["from_iban"],
        "description": doc.get("description", ""),
        "status": doc["status"],
        "created_at": doc["created_at"],
    }


@router.post("/transfers", response_model=TransactionOut, response_model_by_alias=False, status_code=201)
async def create_transfer(payload: TransferRequest, user_id: str = CurrentUserId):
    db = get_database()

    # 1-2. user autentificat (garantat de CurrentUserId) + cont sursă există
    source = await _get_account_by_user(user_id)

    # 3. cont sursă activ
    if source["status"] != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contul sursă nu este activ.")

    # 4. IBAN destinație există
    destination = await _get_account_by_iban(payload.to_iban)
    if destination is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contul destinație nu există.")

    # 5. cont destinație activ
    if destination["status"] != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contul destinație nu este activ.")

    # 6. amount_minor > 0 — garantat de validarea Pydantic (TransferRequest)

    # 7. monedă compatibilă
    if source["currency"] != destination["currency"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Monedele conturilor sursă și destinație diferă.")

    # 8. sold suficient (verificare rapidă — garanția REALĂ, atomică, vine
    # din accounts-service la pasul de aplicare a transferului, mai jos)
    if source["balance_minor"] < payload.amount_minor:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Sold insuficient.")

    # 9. nu permite transfer către același cont
    if source["id"] == destination["id"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nu poți transfera către același cont.")

    # 10. descriere limitată rezonabil — garantat de validarea Pydantic (max_length=140)

    now = datetime.now(timezone.utc)
    transaction_doc = {
        "from_account_id": source["id"],
        "to_account_id": destination["id"],
        "from_iban": source["iban"],
        "to_iban": destination["iban"],
        "amount_minor": payload.amount_minor,
        "currency": source["currency"],
        "description": payload.description,
        "type": "transfer",
        "status": "pending",
        "created_at": now,
    }
    insert_result = await db.transactions.insert_one(transaction_doc)

    try:
        await _apply_transfer(source["id"], destination["id"], payload.amount_minor)
    except HTTPException as exc:
        await db.transactions.update_one({"_id": insert_result.inserted_id}, {"$set": {"status": "failed"}})
        logger.warning(
            "transactions-service: transfer eșuat (tx_id=%s, motiv=%s)",
            insert_result.inserted_id,
            exc.detail,
        )
        raise

    # NU returnăm "completed" înainte ca accounts-service să fi confirmat.
    await db.transactions.update_one({"_id": insert_result.inserted_id}, {"$set": {"status": "completed"}})
    logger.info("transactions-service: transfer reușit (tx_id=%s)", insert_result.inserted_id)

    completed_doc = await db.transactions.find_one({"_id": insert_result.inserted_id})
    return _to_transaction_view(completed_doc, viewer_account_id=source["id"])


@router.get("", response_model=list[TransactionOut], response_model_by_alias=False)
async def list_my_transactions(
    limit: int = Query(default=20, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    user_id: str = CurrentUserId,
):
    db = get_database()
    source = await _get_account_by_user(user_id)

    cursor = (
        db.transactions.find({"$or": [{"from_account_id": source["id"]}, {"to_account_id": source["id"]}]})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )
    docs = await cursor.to_list(length=limit)
    return [_to_transaction_view(doc, viewer_account_id=source["id"]) for doc in docs]


@router.get("/{transaction_id}", response_model=TransactionOut, response_model_by_alias=False)
async def get_transaction(transaction_id: str, user_id: str = CurrentUserId):
    db = get_database()
    source = await _get_account_by_user(user_id)

    try:
        object_id = ObjectId(transaction_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID de tranzacție invalid.") from exc

    doc = await db.transactions.find_one({"_id": object_id})
    if doc is None or source["id"] not in (doc["from_account_id"], doc["to_account_id"]):
        # Nu dezvăluim că tranzacția există dar nu-i aparține — 404 în ambele cazuri.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tranzacția nu există.")

    return _to_transaction_view(doc, viewer_account_id=source["id"])
