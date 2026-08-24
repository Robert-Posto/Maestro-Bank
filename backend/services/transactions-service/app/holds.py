"""Ciclul de viață al unei rețineri (hold) — bani reținuți temporar într-un
cont-pseudo intern (accounts-service::ensure_fraud_holding_account), între
crearea hold-ului (banda de decizie "hold", scor >= prag) și rezolvarea lui
(aprobare de personal, respingere de personal, anulare de client, sau
expirare automată după 24h).

Deliberat SEPARAT de app/fraud/ — acolo e scoring (PUR, fără DB/HTTP),
aici e mișcarea REALĂ a banilor. Fiecare etapă a ciclului de viață
reutilizează EXACT `POST /internal/accounts/transfer`
(accounts-service::apply_internal_transfer) — niciun mecanism nou de
mutare a fondurilor, doar contul-pseudo de reținere ca destinație/sursă
intermediară — vezi planul ("holding account design").

Toate cele 4 căi de rezolvare (customer cancel, staff approve, staff
reject, sweep expirare) trec prin `resolve_hold`, care reclamă hold-ul
ATOMIC (Mongo `find_one_and_update`) ÎNAINTE de a atinge banii — asta e ce
garantează că un hold nu poate fi rezolvat (și banii mutați) de două ori,
indiferent care cale concurentă ajunge prima.
"""

import logging
from datetime import datetime, timedelta, timezone

import httpx
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status

from app.config import settings
from app.database import get_database
from app.fraud.service import record_completed_transfer_for_profile

logger = logging.getLogger("transactions-service")

_HTTP_TIMEOUT_SECONDS = 5.0


def _to_object_id(transaction_id: str) -> ObjectId:
    try:
        return ObjectId(transaction_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tranzacție inexistentă.") from exc


async def _resolve_holding_account_id() -> str:
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        try:
            response = await client.get(f"{settings.accounts_service_url}/internal/accounts/fraud-holding-account")
        except httpx.RequestError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="accounts-service indisponibil.") from exc
    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Eroare la rezolvarea contului de reținere."
        )
    return response.json()["account_id"]


async def _apply_ledger_transfer(from_account_id: str, to_account_id: str, amount_minor: int) -> bool:
    """Întoarce True la succes, False la eșec de BUSINESS (sold insuficient
    / cont inactiv) — NU aruncă pentru acel caz, doar pentru indisponibilitatea
    rețelei, ca apelantul (creare/rezolvare hold) să poată decide următorul
    pas fără să prindă o excepție pentru un caz complet așteptat."""
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        try:
            response = await client.post(
                f"{settings.accounts_service_url}/internal/accounts/transfer",
                json={"from_account_id": from_account_id, "to_account_id": to_account_id, "amount_minor": amount_minor},
            )
        except httpx.RequestError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="accounts-service indisponibil.") from exc
    if response.status_code == 200:
        return True
    if response.status_code == 409:
        return False
    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Eroare la aplicarea mutării de fonduri.")


async def ensure_hold_indexes() -> None:
    """Idempotent — apelată din main.py::lifespan, la fel ca
    fraud/indexes.py::ensure_fraud_indexes. Separată de acel modul, ca
    holds.py să rămână un concern independent (vezi docstring-ul de mai
    sus)."""
    db = get_database()
    await db.transactions.create_index([("status", 1), ("hold.expires_at", 1)])


async def create_hold(*, transaction_id: ObjectId, source_account_id: str, amount_minor: int, evaluated_at: datetime) -> None:
    """Apelat DOAR din service.py::create_transfer, când banda calculată e
    "hold" și aplicarea reală e activă (not settings.fraud_shadow_mode).
    Aruncă HTTPException(409) la eșec de debit — EXACT același contract ca
    _apply_transfer din service.py, ca create_transfer să poată reutiliza
    identic try/except-ul deja existent, indiferent de ramură."""
    holding_account_id = await _resolve_holding_account_id()
    debited = await _apply_ledger_transfer(source_account_id, holding_account_id, amount_minor)
    if not debited:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Sold insuficient sau cont sursă inactiv.")

    db = get_database()
    expires_at = evaluated_at + timedelta(hours=settings.hold_ttl_hours)
    await db.transactions.update_one(
        {"_id": transaction_id},
        {
            "$set": {
                "status": "pending_review",
                "hold": {
                    "holding_account_id": holding_account_id,
                    "expires_at": expires_at,
                    "resolution": None,
                    "resolved_by": None,
                    "resolved_at": None,
                },
            }
        },
    )
    logger.info("transactions-service: hold creat (tx_id=%s, expires_at=%s)", transaction_id, expires_at)


async def resolve_hold(transaction_id_str: str, *, resolution: str, resolved_by: str) -> dict:
    """Motorul comun al celor 4 căi de rezolvare. `resolution` e
    "released" (banii AJUNG la beneficiarul real — aprobare de personal)
    sau "cancelled"/"expired" (banii se ÎNTORC la expeditor — respingere
    de personal, anulare de client, sau sweep de expirare).

    Reclamă hold-ul ATOMIC (filtrul cere explicit status="pending_review"
    ȘI hold.resolution=None) ÎNAINTE de a mișca vreun ban — asta previne
    dublă-mutare de fonduri dacă două căi de rezolvare ajung concurent
    (ex. personalul aprobă exact când sweep-ul de expirare rulează)."""
    object_id = _to_object_id(transaction_id_str)
    db = get_database()
    now = datetime.now(timezone.utc)

    claim = await db.transactions.find_one_and_update(
        {"_id": object_id, "status": "pending_review", "hold.resolution": None},
        {"$set": {"hold.resolution": "in_progress", "hold.resolved_by": resolved_by, "hold.resolved_at": now}},
    )
    if claim is None:
        existing = await db.transactions.find_one({"_id": object_id})
        if existing is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tranzacție inexistentă.")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Această reținere nu (mai) este în așteptare."
        )

    holding_account_id = claim["hold"]["holding_account_id"]
    amount_minor = claim["amount_minor"]
    primary_target = claim["to_account_id"] if resolution == "released" else claim["from_account_id"]

    final_resolution = resolution
    if not await _apply_ledger_transfer(holding_account_id, primary_target, amount_minor):
        # Doar "released" are un fallback cu sens (întoarce la sursă în loc
        # de beneficiar) — "cancelled"/"expired" ȚINTESC DEJA sursa, deci un
        # eșec acolo nu are unde să mai cadă înapoi.
        fallback_succeeded = resolution == "released" and await _apply_ledger_transfer(
            holding_account_id, claim["from_account_id"], amount_minor
        )
        if not fallback_succeeded:
            await db.transactions.update_one({"_id": object_id}, {"$set": {"hold.resolution": "stuck"}})
            logger.critical(
                "transactions-service: fonduri BLOCATE în contul de reținere (tx_id=%s, holding_account_id=%s, "
                "amount_minor=%s) — nici eliberarea, nici reîntoarcerea la sursă nu au reușit, necesită "
                "intervenție manuală",
                transaction_id_str,
                holding_account_id,
                amount_minor,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail="Eroare la rezolvarea reținerii — contactează suportul."
            )
        final_resolution = "expired"

    await db.transactions.update_one(
        {"_id": object_id},
        {
            "$set": {
                "status": "completed" if final_resolution == "released" else "cancelled",
                "hold.resolution": final_resolution,
            }
        },
    )

    if final_resolution == "released":
        # Reținerea s-a rezolvat cu fondurile CHIAR ajunse la beneficiar —
        # acum e "comportament normal confirmat", exact ca un transfer
        # obișnuit — vezi service.py::create_transfer, hook-ul 2 (profilul
        # NU a fost actualizat la creare hold, deliberat — vezi acolo).
        # Best-effort: un profil neactualizat doar degradează spre cold
        # start la următoarea evaluare, nu strică rezolvarea hold-ului.
        try:
            await _update_profile_after_release(claim)
        except Exception as exc:
            logger.warning("transactions-service: actualizare profil eșuată după eliberare hold (tx_id=%s): %s", transaction_id_str, exc)

    return await db.transactions.find_one({"_id": object_id})


async def _update_profile_after_release(transaction: dict) -> None:
    db = get_database()
    evaluation = await db.fraud_evaluations.find_one({"transaction_id": transaction["_id"]})
    if evaluation is None:
        return  # motorul de fraud era dezactivat la momentul creării — nimic de actualizat
    await record_completed_transfer_for_profile(
        user_id=evaluation["user_id"], transaction=transaction, evaluated_at=datetime.now(timezone.utc)
    )


async def approve_hold(transaction_id: str, staff_user_id: str) -> dict:
    return await resolve_hold(transaction_id, resolution="released", resolved_by=staff_user_id)


async def reject_hold(transaction_id: str, staff_user_id: str) -> dict:
    return await resolve_hold(transaction_id, resolution="cancelled", resolved_by=staff_user_id)


async def cancel_hold(transaction_id: str) -> dict:
    return await resolve_hold(transaction_id, resolution="cancelled", resolved_by="customer")


async def sweep_expired_holds() -> int:
    """Apelată periodic din app/scheduler.py::hold_expiry_loop. Idempotentă
    prin construcție — resolve_hold reclamă atomic, deci a rula sweep-ul de
    două ori (sau simultan cu o rezolvare manuală) e sigur."""
    db = get_database()
    now = datetime.now(timezone.utc)
    due = await db.transactions.find(
        {"status": "pending_review", "hold.resolution": None, "hold.expires_at": {"$lte": now}}, {"_id": 1}
    ).to_list(length=1000)

    processed = 0
    for doc in due:
        try:
            await resolve_hold(str(doc["_id"]), resolution="expired", resolved_by="system")
            processed += 1
        except HTTPException as exc:
            logger.warning("transactions-service: sweep nu a putut rezolva hold-ul %s: %s", doc["_id"], exc.detail)
    return processed


async def _fetch_user_contact(user_id: str) -> dict | None:
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        try:
            response = await client.get(f"{settings.auth_service_url}/internal/users/{user_id}/contact")
        except httpx.RequestError:
            return None
    if response.status_code != 200:
        return None
    return response.json()


async def list_pending_holds() -> list[dict]:
    """Pentru personal — vezi routers/staff.py. Fiecare hold "pending_review"
    ÎMPREUNĂ cu scorul/regulile lui (din fraud_evaluations, legate prin
    transaction_id) și datele de contact ale clientului (din auth-service,
    prin user_id — disponibil DOAR pe fraud_evaluations, nu pe tranzacție
    în sine, care nu ține user_id direct)."""
    db = get_database()
    holds = (
        await db.transactions.find({"status": "pending_review", "hold.resolution": None})
        .sort("created_at", 1)
        .to_list(length=200)
    )
    if not holds:
        return []

    tx_ids = [h["_id"] for h in holds]
    evaluations = await db.fraud_evaluations.find({"transaction_id": {"$in": tx_ids}}).to_list(length=len(tx_ids))
    evaluations_by_tx = {e["transaction_id"]: e for e in evaluations}

    composed: list[dict] = []
    for hold in holds:
        evaluation = evaluations_by_tx.get(hold["_id"])
        contact = await _fetch_user_contact(evaluation["user_id"]) if evaluation else None
        composed.append(
            {
                "id": str(hold["_id"]),
                "from_iban": hold["from_iban"],
                "to_iban": hold["to_iban"],
                "from_name": hold.get("from_name"),
                "to_name": hold.get("to_name"),
                "amount_minor": hold["amount_minor"],
                "currency": hold["currency"],
                "description": hold.get("description", ""),
                "category": hold.get("category", "other"),
                "status": hold["status"],
                "created_at": hold["created_at"],
                "hold_expires_at": hold.get("hold", {}).get("expires_at"),
                "score": evaluation["score"] if evaluation else None,
                "fired_rule_ids": [r["rule_id"] for r in evaluation["fired_rules"]] if evaluation else [],
                "customer": contact,
            }
        )
    return composed
