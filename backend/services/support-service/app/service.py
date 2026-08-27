"""Logica de business a support-service.

Separată de routing (`app/routers/support.py`, care doar validează
input-ul și deleagă aici) și de modele (`app/models.py`). Acest modul e
singurul care atinge `db.tickets`/`db.documents` direct.
"""

import logging
from datetime import datetime, timezone

import httpx
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status

from app.config import settings
from app.database import get_database
from app.models import DocumentCreate, DocumentSignRequest, NotificationCreate, TicketCreate

logger = logging.getLogger("support-service")


async def create_ticket(user_id: str, payload: TicketCreate) -> dict:
    db = get_database()
    now = datetime.now(timezone.utc)
    doc = {
        "user_id": user_id,
        "subject": payload.subject,
        "category": payload.category,
        "message": payload.message,
        "status": "open",
        "created_at": now,
        "updated_at": now,
    }
    result = await db.tickets.insert_one(doc)
    logger.info("support-service: ticket creat (id=%s, user_id=%s, category=%s)", result.inserted_id, user_id, payload.category)
    return await db.tickets.find_one({"_id": result.inserted_id})


async def list_tickets_for_user(user_id: str) -> list[dict]:
    db = get_database()
    cursor = db.tickets.find({"user_id": user_id}).sort("created_at", -1)
    return await cursor.to_list(length=200)


async def get_ticket_for_user(ticket_id: str, user_id: str) -> dict:
    db = get_database()
    try:
        object_id = ObjectId(ticket_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID de tichet invalid.") from exc

    doc = await db.tickets.find_one({"_id": object_id})
    if doc is None or doc["user_id"] != user_id:
        # Nu dezvăluim că tichetul există dar nu-i aparține — 404 în ambele cazuri.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tichetul nu există.")
    return doc


# --- Notificări -------------------------------------------------------------


async def create_notification(payload: NotificationCreate) -> dict:
    """Apelat DOAR intern, de alte servicii (accounts/budgets/transactions) —
    vezi app/routers/notifications.py. Userul nu poate crea notificări direct."""
    db = get_database()
    doc = {
        "user_id": payload.user_id,
        "kind": payload.kind,
        "text": payload.text,
        "read": False,
        "created_at": datetime.now(timezone.utc),
        "reference_id": payload.reference_id,
    }
    result = await db.notifications.insert_one(doc)
    logger.info("support-service: notificare creată (user_id=%s, kind=%s)", payload.user_id, payload.kind)
    return await db.notifications.find_one({"_id": result.inserted_id})


async def list_notifications_for_user(user_id: str) -> list[dict]:
    db = get_database()
    cursor = db.notifications.find({"user_id": user_id}).sort("created_at", -1).limit(30)
    return await cursor.to_list(length=30)


async def mark_all_read(user_id: str) -> None:
    db = get_database()
    await db.notifications.update_many({"user_id": user_id, "read": False}, {"$set": {"read": True}})


async def delete_notification(notification_id: str, user_id: str) -> None:
    """Șterge o singură notificare a userului curent.

    `user_id` intră în filtrul de ștergere, nu doar într-o verificare
    ulterioară — așa nu există fereastră în care altcineva ar putea șterge
    notificarea altui user, indiferent de ce id trimite.
    """
    db = get_database()
    try:
        object_id = ObjectId(notification_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID de notificare invalid.") from exc

    result = await db.notifications.delete_one({"_id": object_id, "user_id": user_id})
    if result.deleted_count == 0:
        # Nu dezvăluim că notificarea există dar aparține altcuiva — 404 în
        # ambele cazuri, la fel ca la tichete (vezi get_ticket_for_user).
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notificarea nu există.")


async def ensure_document_indexes() -> None:
    db = get_database()
    await db.documents.create_index("user_id")
    await db.documents.create_index("staff_user_id")


# --- Documente de semnat (eSign) -----------------------------------------
#
# support-service nu deține `users` — orice rezolvare de identitate
# (căutare client, nume pentru afișare, verificare parolă/passkey la
# semnare) trece printr-un apel HTTP intern către auth-service, la fel ca
# _verify_webauthn_with_auth_service din accounts-service (card_reveal).


async def search_customers(query: str) -> list[dict]:
    """Proxy către auth-service::search_users — support-service nu deține
    `users`, doar documente. Folosit de personal la trimiterea unui
    document nou (căutare de la zero, fără user_id cunoscut în avans)."""
    trimmed = query.strip()
    if not trimmed:
        return []
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.auth_service_url}/internal/users/search", params={"q": trimmed})
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("support-service: căutarea de clienți a eșuat: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Nu am putut căuta clienți — serviciul de autentificare este indisponibil.",
        ) from exc
    return response.json()


async def _resolve_customer_name(user_id: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.auth_service_url}/internal/users/{user_id}/contact")
    except httpx.HTTPError as exc:
        logger.error("support-service: auth-service indisponibil la rezolvarea clientului: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Serviciul de autentificare este indisponibil."
        ) from exc

    if response.status_code == status.HTTP_404_NOT_FOUND:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Clientul nu există.")
    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID de client invalid.")

    contact = response.json()
    return f"{contact['first_name']} {contact['last_name']}"


async def create_document(payload: DocumentCreate, staff_user_id: str) -> dict:
    """Trimite un document unui client — vezi routers/staff.py. Numele
    clientului e rezolvat AICI, o singură dată, și stocat pe document
    (`customer_name`) — ca listarea ulterioară de personal (list_documents_
    for_staff) să nu facă un apel HTTP separat pentru fiecare rând."""
    customer_name = await _resolve_customer_name(payload.user_id)

    db = get_database()
    now = datetime.now(timezone.utc)
    doc = {
        "user_id": payload.user_id,
        "staff_user_id": staff_user_id,
        "customer_name": customer_name,
        "title": payload.title,
        "pdf_data": payload.pdf_data,
        "status": "pending",
        "created_at": now,
        "signed_at": None,
        "sign_method": None,
    }
    result = await db.documents.insert_one(doc)
    logger.info(
        "support-service: document trimis (id=%s, user_id=%s, staff_user_id=%s)",
        result.inserted_id, payload.user_id, staff_user_id,
    )

    await create_notification(
        NotificationCreate(
            user_id=payload.user_id, kind="document_sign", text=f"Ai un document nou de semnat: {payload.title}"
        )
    )

    return await db.documents.find_one({"_id": result.inserted_id})


async def list_documents_for_user(user_id: str) -> list[dict]:
    db = get_database()
    cursor = db.documents.find({"user_id": user_id}, {"pdf_data": 0}).sort("created_at", -1)
    return await cursor.to_list(length=200)


async def get_document_for_user(document_id: str, user_id: str) -> dict:
    db = get_database()
    try:
        object_id = ObjectId(document_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID de document invalid.") from exc

    doc = await db.documents.find_one({"_id": object_id})
    if doc is None or doc["user_id"] != user_id:
        # Nu dezvăluim că documentul există dar aparține altcuiva — 404 în
        # ambele cazuri, la fel ca la tichete/notificări.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documentul nu există.")
    return doc


async def _verify_password_with_auth_service(user_id: str, password: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{settings.auth_service_url}/internal/auth/verify-password",
                json={"user_id": user_id, "password": password},
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("support-service: verificarea parolei a eșuat (user_id=%s): %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Serviciul de autentificare este indisponibil."
        ) from exc
    return bool(response.json().get("valid", False))


async def _verify_webauthn_with_auth_service(user_id: str, document_id: str, challenge_id: str, assertion: dict) -> bool:
    """`document_id` e valoarea REZOLVATĂ server-side (documentul deja găsit
    în sign_document, înainte de acest apel) — niciodată una trimisă direct
    de client — ca action_payload din challenge-ul de step-up, la fel ca la
    card_reveal (accounts-service). Un assertion capturat pentru documentul
    A nu poate fi refolosit ca să semneze documentul B."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{settings.auth_service_url}/internal/auth/verify-webauthn",
                json={
                    "user_id": user_id,
                    "challenge_id": challenge_id,
                    "action": "document_sign",
                    "action_payload": document_id,
                    "credential": assertion,
                },
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("support-service: verificarea passkey-ului a eșuat (user_id=%s): %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Nu am putut verifica passkey-ul — serviciul de autentificare este indisponibil.",
        ) from exc
    return bool(response.json().get("valid", False))


async def sign_document(document_id: str, user_id: str, payload: DocumentSignRequest) -> dict:
    """Semnează un document — reconfirmare de identitate obligatorie
    (parolă SAU passkey, vezi DocumentSignRequest), la fel ca reveal_card
    din accounts-service. „Semnătura" propriu-zisă e acest eveniment de
    audit (cine, când, prin ce metodă), nu o semnătură grafică.

    Notă de transparență: verificarea prin parolă (/internal/auth/
    verify-password) confirmă DOAR parola contului, fără legare de
    action/action_payload (spre deosebire de calea WebAuthn) — un cuplu
    parolă+document_id nu poate fi „replay"-uit către alt document oricum,
    pentru că verificăm local, mai jos, că documentul e "pending" și
    aparține userului curent — dar proprietatea criptografică de legare
    lipseşte pe calea cu parolă, exact ca la orice alt consumator posibil
    al acelei rute."""
    document = await get_document_for_user(document_id, user_id)
    if document["status"] != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Documentul nu mai poate fi semnat (deja semnat sau anulat)."
        )

    if payload.password is not None:
        ok = await _verify_password_with_auth_service(user_id, payload.password)
        sign_method = "password"
        error_detail = "Parolă incorectă."
    else:
        ok = await _verify_webauthn_with_auth_service(
            user_id, document_id, payload.webauthn_challenge_id, payload.webauthn_assertion
        )
        sign_method = "webauthn"
        error_detail = "Confirmarea biometrică a eșuat."

    if not ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error_detail)

    db = get_database()
    object_id = ObjectId(document_id)
    now = datetime.now(timezone.utc)
    await db.documents.update_one({"_id": object_id}, {"$set": {"status": "signed", "signed_at": now, "sign_method": sign_method}})
    logger.info("support-service: document semnat (id=%s, user_id=%s, method=%s)", document_id, user_id, sign_method)
    return await db.documents.find_one({"_id": object_id}, {"pdf_data": 0})


async def list_documents_for_staff(limit: int = 100, skip: int = 0) -> list[dict]:
    db = get_database()
    cursor = db.documents.find({}, {"pdf_data": 0}).sort("created_at", -1).skip(skip).limit(min(limit, 100))
    return await cursor.to_list(length=100)


async def cancel_document(document_id: str, staff_user_id: str) -> None:
    """Orice membru al personalului poate anula orice document în
    așteptare — la fel ca la aprobarea/respingerea unei rețineri de
    fraudă, acțiunile de personal nu sunt restricționate la cel care a
    inițiat (consolă comună, nu proprietate individuală)."""
    db = get_database()
    try:
        object_id = ObjectId(document_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID de document invalid.") from exc

    doc = await db.documents.find_one({"_id": object_id})
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documentul nu există.")
    if doc["status"] != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Doar documentele în așteptare pot fi anulate.")

    await db.documents.update_one({"_id": object_id}, {"$set": {"status": "cancelled"}})
    logger.info("support-service: document anulat (id=%s, staff_user_id=%s)", document_id, staff_user_id)
