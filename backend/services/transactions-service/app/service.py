"""Logica de business a transactions-service.

Separată de routing (`app/routers/transfers.py`, care doar validează
input-ul și deleagă aici) și de modele (`app/models.py`). Acest modul e
singurul care atinge `db.transactions` direct.

Acest serviciu NU citește niciodată direct accounts_db — orice informație
despre conturi (sold, status, IBAN) vine prin API-ul accounts-service,
folosind adresa internă Docker (`http://accounts-service:8000`), NEVER
localhost. Vezi `_get_account_by_user` / `_get_account_by_iban` /
`_apply_transfer` mai jos.
"""

import asyncio
import calendar
import csv
import io
import logging
from datetime import datetime, timedelta, timezone

import httpx
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import BackgroundTasks, HTTPException, status

from app import content_screening, holds
from app.config import settings
from app.database import get_database
from app.fraud.service import evaluate_and_record_transfer_risk, record_completed_transfer_for_profile
from app.guardian import service as guardian_service
from app.money import format_minor_amount
from app.models import (
    PaymentRequestCreate,
    ReportTransactionRequest,
    ScheduledTransferCreate,
    TransactionFilters,
    TransferRequest,
)

logger = logging.getLogger("transactions-service")


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


async def _get_user_name(user_id: str) -> str | None:
    """Rezolvă "Prenume Nume" pentru un user real, prin auth-service.

    Întoarce None dacă lookup-ul eșuează — ex. contrapartida e un cont-
    pseudo de comerciant (fără user real în auth_db), sau auth-service e
    indisponibil. Degradare grațioasă: frontendul cade atunci înapoi pe
    descriere/IBAN, exact ca înainte (vezi to_transaction_view).
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.auth_service_url}/internal/users/{user_id}")
        if response.status_code == 200:
            body = response.json()
            return f"{body['first_name']} {body['last_name']}"
    except httpx.RequestError:
        logger.warning("transactions-service: auth-service indisponibil la rezolvarea numelui (user_id=%s)", user_id)
    return None


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


def check_description_content(description: str) -> str | None:
    """Verificare LIVE, apelată de frontend pe măsură ce userul scrie în
    câmpul de descriere (vezi app/routers/transfers.py, POST
    /transfers/screen-description) — ACELAȘI screening determinist ca la
    crearea reală a transferului (vezi content_screening.py), dar fără
    NICIUN efect secundar (nu scrie nimic în DB, nu creează nimic). Nu
    necesită user_id — nu accesează date de cont, doar textul primit."""
    return content_screening.screen_description(description)


def to_transaction_view(doc: dict, viewer_account_id: str) -> dict:
    is_outgoing = doc["from_account_id"] == viewer_account_id
    return {
        "_id": doc["_id"],
        "direction": "outgoing" if is_outgoing else "incoming",
        "amount_minor": doc["amount_minor"],
        "amount": format_minor_amount(doc["amount_minor"]),
        "currency": doc["currency"],
        "counterparty_iban": doc["to_iban"] if is_outgoing else doc["from_iban"],
        # Nume "Prenume Nume" al contrapărții, DOAR dacă e un user real —
        # salvat ca snapshot la creare transfer (vezi create_transfer),
        # nu recalculat live. None pentru plăți către comercianți/nume
        # care nu au fost rezolvate — frontendul cade pe descriere/IBAN.
        "counterparty_name": doc.get("to_name") if is_outgoing else doc.get("from_name"),
        "description": doc.get("description", ""),
        "category": doc.get("category", "other"),
        "status": doc["status"],
        "recognized": doc.get("recognized", False),
        "reported": doc.get("reported", False),
        "created_at": doc["created_at"],
        "hold": doc.get("hold"),
        # Evaluarea de risc e despre COMPORTAMENTUL EXPEDITORULUI (sumă
        # neobișnuită pentru EL, beneficiar nou pentru EL etc.) — n-are
        # niciun sens pentru cine PRIMEȘTE banii, și i-ar arăta un card
        # "Financial Guardian" despre o tranzacție la care n-a făcut
        # nimic neobișnuit. Vizibil DOAR pe partea de expeditor.
        "risk": doc.get("risk") if is_outgoing else None,
    }


async def create_transfer(
    payload: TransferRequest, user_id: str, background_tasks: BackgroundTasks | None = None
) -> dict:
    # `background_tasks` vine din routers/transfers.py (Starlette îl
    # rulează automat DUPĂ ce răspunsul e trimis) când apelul pornește
    # dintr-o cerere HTTP reală. run_due_scheduled_transfers (mai jos, în
    # acest fișier) apelează create_transfer DIN INTERIORUL unui loop de
    # fundal, fără nicio cerere HTTP — acolo nu există niciun ciclu de
    # răspuns ASGI care să-l ruleze automat, deci ne creăm propria instanță
    # și o așteptăm explicit înainte de return.
    owns_background_tasks = background_tasks is None
    if owns_background_tasks:
        background_tasks = BackgroundTasks()
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

    # Nume snapshot pentru contrapartidă (afișat în UI în loc de IBAN brut —
    # ex. "Ai primit 100 RON de la Andrei Popescu"). Rezolvat o singură
    # dată, la creare, prin auth-service — None pentru conturi fără user
    # real (comercianți), degradare grațioasă dacă auth-service pică.
    from_name, to_name = await asyncio.gather(
        _get_user_name(source["user_id"]),
        _get_user_name(destination["user_id"]),
    )

    now = datetime.now(timezone.utc)
    # Screening determinist al descrierii (termeni de terorism/violență —
    # vezi app/content_screening.py) — NU blochează transferul, doar
    # informează userul; complet separat de motorul de fraudă (app/fraud/).
    content_warning = content_screening.screen_description(payload.description)
    if content_warning:
        logger.warning(
            "transactions-service: descriere transfer cu termeni marcați (user_id=%s) — transferul continuă normal",
            user_id,
        )
    transaction_doc = {
        "from_account_id": source["id"],
        "to_account_id": destination["id"],
        "from_iban": source["iban"],
        "to_iban": destination["iban"],
        "from_name": from_name,
        "to_name": to_name,
        "amount_minor": payload.amount_minor,
        "currency": source["currency"],
        "description": payload.description,
        "category": payload.category,
        "type": "transfer",
        "status": "pending",
        "recognized": False,
        "reported": False,
        "created_at": now,
        "content_warning": content_warning,
    }
    insert_result = await db.transactions.insert_one(transaction_doc)

    # Scor fraud + audit. Când `fraud_shadow_mode` e activ (Faza 1), banda
    # întoarsă e ÎNTOTDEAUNA None — create_transfer nu are cum să ramifice
    # pe ea, vezi garanția structurală din app/fraud/service.py. Când
    # aplicarea reală e activă, banda "hold" chiar gatează ramura de mai
    # jos — restul benzilor (None/pass/notify/step_up) nu schimbă nimic
    # încă (vezi planul fazei — doar 80+ are aplicare reală acum).
    decision_band: str | None = None
    try:
        decision_band = await evaluate_and_record_transfer_risk(
            transaction_id=insert_result.inserted_id,
            transaction=transaction_doc,
            source_account=source,
            user_id=user_id,
            evaluated_at=now,
        )
    except Exception:
        logger.critical(
            "transactions-service: evaluate_and_record_transfer_risk a scăpat o excepție netratată "
            "(tx_id=%s) — nu ar trebui să fie posibil, vezi app/fraud/service.py",
            insert_result.inserted_id,
        )

    is_held = decision_band == "hold"

    # Guardian (app/guardian/) — explicația LLM a deciziei de mai sus, NU
    # o a doua decizie. `informational_band` e citit din fraud_evaluations
    # (scris NECONDIȚIONAT de audit.py, indiferent de shadow mode) — spre
    # deosebire de `decision_band` de mai sus, care rămâne mereu None sub
    # shadow mode, prin garanția proprie a evaluate_and_record_transfer_
    # risk (nemodificată aici). Cele două servesc scopuri diferite: `is_held`
    # gatează banii (deja calculat mai sus), `informational_band` gatează
    # DOAR ce vede clientul despre risc — vezi guardian/service.py pentru
    # de ce nu sunt același lucru sub shadow mode.
    if settings.guardian_enabled:
        evaluation_doc = await db.fraud_evaluations.find_one({"transaction_id": insert_result.inserted_id})
        informational_band = evaluation_doc.get("decision_would_apply") if evaluation_doc else None

        risk = guardian_service.compute_customer_risk(informational_band, is_held)
        await db.transactions.update_one({"_id": insert_result.inserted_id}, {"$set": {"risk": risk}})

        guardian_scope = guardian_service._CUSTOMER_PHRASE_BANDS | set(settings.guardian_staff_report_bands)
        if informational_band in guardian_scope:
            background_tasks.add_task(
                guardian_service.generate_guardian_explanations,
                transaction_id=insert_result.inserted_id,
                user_id=user_id,
            )

    try:
        if is_held:
            await holds.create_hold(
                transaction_id=insert_result.inserted_id,
                source_account_id=source["id"],
                amount_minor=payload.amount_minor,
                evaluated_at=now,
            )
        else:
            await _apply_transfer(source["id"], destination["id"], payload.amount_minor)
    except HTTPException as exc:
        await db.transactions.update_one({"_id": insert_result.inserted_id}, {"$set": {"status": "failed"}})
        logger.warning(
            "transactions-service: transfer eșuat (tx_id=%s, motiv=%s)",
            insert_result.inserted_id,
            exc.detail,
        )
        raise

    if is_held:
        # NU marcăm "completed" — holds.create_hold a setat deja
        # status="pending_review" + hold{...}. NU actualizăm profilul —
        # un transfer reținut, nerezolvat încă, nu e "comportament normal
        # confirmat" (vezi app/fraud/profile.py).
        logger.info("transactions-service: transfer reținut pentru revizuire (tx_id=%s)", insert_result.inserted_id)
        await _notify_user(
            user_id,
            "transfer_hold",
            f"Transferul de {format_minor_amount(payload.amount_minor)} {source['currency']} către "
            f"{payload.to_iban} este în verificare de securitate — vei fi anunțat imediat ce e rezolvat.",
        )
    else:
        # NU returnăm "completed" înainte ca accounts-service să fi confirmat.
        await db.transactions.update_one({"_id": insert_result.inserted_id}, {"$set": {"status": "completed"}})
        logger.info("transactions-service: transfer reușit (tx_id=%s)", insert_result.inserted_id)

        await _notify_user(
            user_id,
            "transfer",
            f"Transfer de {format_minor_amount(payload.amount_minor)} {source['currency']} către {payload.to_iban} — reușit.",
        )

        # Destinatarul primea bani fără NICIO notificare — doar expeditorul
        # era anunțat mai sus. Excepție: transfer între propriile conturi
        # (destination["user_id"] == user_id) — notificarea de mai sus e
        # deja suficientă, a doua ar fi doar zgomot ("ai primit de la tine").
        if destination["user_id"] != user_id:
            await _notify_user(
                destination["user_id"],
                "transfer_received",
                f"Ai primit {format_minor_amount(payload.amount_minor)} {source['currency']} de la {from_name or source['iban']}.",
            )

        # Profilul fraud (percentile/istoric categorii/țări cunoscute) se
        # actualizează DOAR la transferuri efectiv "completed" — vezi
        # app/fraud/profile.py. Best-effort, la fel ca _notify_user: un
        # profil stale/lipsă doar degradează spre cold start la
        # următoarea evaluare.
        try:
            await record_completed_transfer_for_profile(user_id=user_id, transaction=transaction_doc, evaluated_at=now)
        except Exception:
            logger.warning(
                "transactions-service: record_completed_transfer_for_profile a scăpat o excepție netratată (tx_id=%s)",
                insert_result.inserted_id,
            )

    final_doc = await db.transactions.find_one({"_id": insert_result.inserted_id})
    view = to_transaction_view(final_doc, viewer_account_id=source["id"])

    if owns_background_tasks:
        # Niciun ciclu de răspuns ASGI care să ruleze background_tasks
        # automat aici (vezi comentariul de la începutul funcției) — îl
        # rulăm noi explicit, DUPĂ ce documentul final e deja citit.
        await background_tasks()

    return view


async def cancel_own_hold(transaction_id: str, user_id: str) -> dict:
    """Clientul își anulează PROPRIA reținere — nu are nevoie de WebAuthn
    (anularea e direcția sigură: banii se întorc la el, nu pleacă mai
    departe — vezi planul, "self-service release" e amânat, dar cancel nu).
    Verificarea de proprietate rezolvă contul curent al userului AUTENTIFICAT
    (din JWT, niciodată dintr-un câmp trimis de client) și confirmă că
    EXACT acel cont e sursa hold-ului, exact ca la restul rutelor "userul
    meu" din acest fișier."""
    source = await _get_account_by_user(user_id)

    try:
        object_id = ObjectId(transaction_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tranzacție inexistentă.") from exc

    db = get_database()
    transaction = await db.transactions.find_one({"_id": object_id})
    if transaction is None or transaction["from_account_id"] != source["id"]:
        # 404, nu 403 — nu confirmăm existența unei tranzacții a altcuiva.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tranzacție inexistentă.")

    updated_doc = await holds.cancel_hold(transaction_id)
    logger.info("transactions-service: hold anulat de client (tx_id=%s)", transaction_id)
    await _notify_user(
        user_id, "transfer_hold_cancelled", "Ai anulat transferul reținut — fondurile au revenit în cont."
    )
    return to_transaction_view(updated_doc, viewer_account_id=source["id"])


async def _notify_user(user_id: str, kind: str, text: str) -> None:
    """Trimite o notificare persistentă către support-service. NU blochează
    și NU eșuează operația principală dacă support-service e indisponibil —
    la fel ca provisioning-ul de cont din auth-service, o notificare
    pierdută nu trebuie să strice fluxul de bani."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post(
                f"{settings.support_service_url}/internal/notifications",
                json={"user_id": user_id, "kind": kind, "text": text},
            )
    except httpx.HTTPError:
        logger.warning("transactions-service: notificare eșuată (user_id=%s, kind=%s)", user_id, kind)


# --- Transferuri programate/recurente ---------------------------------------


def _advance_schedule(current: datetime, frequency: str) -> datetime:
    if frequency == "weekly":
        return current + timedelta(days=7)

    # monthly — păstrează ziua din lună, cu clamp la ultima zi validă (ex.
    # 31 ianuarie -> 28/29 februarie), nu explodează cu ValueError.
    month = current.month + 1
    year = current.year + (month - 1) // 12
    month = ((month - 1) % 12) + 1
    day = min(current.day, calendar.monthrange(year, month)[1])
    return current.replace(year=year, month=month, day=day)


async def create_scheduled_transfer(user_id: str, payload: ScheduledTransferCreate) -> dict:
    db = get_database()
    now = datetime.now(timezone.utc)
    doc = {
        "user_id": user_id,
        "to_iban": payload.to_iban,
        "amount_minor": payload.amount_minor,
        "description": payload.description,
        "frequency": payload.frequency,
        "next_run_at": _advance_schedule(now, payload.frequency),
        "active": True,
        "created_at": now,
    }
    result = await db.scheduled_transfers.insert_one(doc)
    return await db.scheduled_transfers.find_one({"_id": result.inserted_id})


async def list_scheduled_transfers_for_user(user_id: str) -> list[dict]:
    db = get_database()
    cursor = db.scheduled_transfers.find({"user_id": user_id, "active": True}).sort("next_run_at", 1)
    return await cursor.to_list(length=50)


async def cancel_scheduled_transfer(schedule_id: str, user_id: str) -> None:
    db = get_database()
    try:
        object_id = ObjectId(schedule_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID de transfer programat invalid.") from exc

    result = await db.scheduled_transfers.update_one(
        {"_id": object_id, "user_id": user_id, "active": True},
        {"$set": {"active": False}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transferul programat nu există.")


async def run_due_scheduled_transfers() -> None:
    """Apelat periodic dintr-un loop intern (vezi app/scheduler.py, pornit
    din app/main.py::lifespan) — execută orice transfer programat cu
    `next_run_at` scadent, REFOLOSIND `create_transfer` (aceeași validare,
    exact același flux ca un transfer manual — inclusiv notificarea).

    Un eșec la UN schedule (ex. sold insuficient în acel moment) nu oprește
    restul — se loghează și se reîncearcă la următoarea rulare programată,
    nu imediat (evită retry-storm dacă userul rămâne fără fonduri).
    """
    db = get_database()
    now = datetime.now(timezone.utc)
    due = await db.scheduled_transfers.find({"active": True, "next_run_at": {"$lte": now}}).to_list(length=200)

    for schedule in due:
        transfer_payload = TransferRequest(
            to_iban=schedule["to_iban"],
            amount_minor=schedule["amount_minor"],
            description=schedule["description"] or "Transfer programat",
        )
        try:
            await create_transfer(transfer_payload, schedule["user_id"])
            logger.info("transactions-service: transfer programat executat (id=%s)", schedule["_id"])
        except HTTPException as exc:
            logger.warning(
                "transactions-service: transfer programat eșuat (id=%s, motiv=%s) — reîncerc la următoarea rulare",
                schedule["_id"],
                exc.detail,
            )

        next_run = _advance_schedule(schedule["next_run_at"], schedule["frequency"])
        await db.scheduled_transfers.update_one({"_id": schedule["_id"]}, {"$set": {"next_run_at": next_run}})


# --- Cereri de plată (link/QR de tip "Request Money", ca la Revolut) ------
#
# Vezi PaymentRequestCreate/PaymentRequestOut din app/models.py pentru
# designul complet. Plata efectivă (pay_payment_request) REFOLOSEȘTE
# create_transfer de mai sus — aceeași validare, screening de conținut,
# motor de fraudă, Guardian — nu duplică nimic din fluxul de bani.

_PAYMENT_REQUEST_EXPIRY_DAYS = 7


def _payment_request_effective_status(doc: dict, now: datetime) -> str:
    """Starea REALĂ, calculată la citire — două cazuri unde câmpul brut din
    DB nu reflectă direct realitatea:

    - "processing" e o stare TRANZITORIE internă (vezi pay_payment_request,
      claim atomic anti-double-spend) — invizibilă în afara acestui modul,
      arătată clientului tot ca "open" (din perspectiva lui, cererea încă
      se poate plăti, doar că o altă plată e chiar acum în curs).
    - Expirarea e LENEȘĂ (calculată aici, fără loop de fundal) — spre
      deosebire de hold-uri (app/holds.py), o cerere de plată expirată nu
      mișcă bani, deci nu e nimic de "rezolvat" la expirare, doar de
      ascuns din UI ca opțiune de plată.
    """
    status_value = doc["status"]
    if status_value == "processing":
        return "open"
    # Motor/PyMongo întoarce datetime-urile citite din Mongo NAIVE (fără
    # tzinfo, chiar dacă valoarea e UTC) — spre deosebire de `now`, mereu
    # tz-aware aici. Comparația directă ar arunca TypeError; normalizăm
    # înainte de comparat (vezi și app/holds.py, care evită complet
    # problema comparând server-side, în query-ul Mongo).
    expires_at = doc["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if status_value == "open" and now > expires_at:
        return "expired"
    return status_value


def _to_payment_request_view(doc: dict, now: datetime | None = None) -> dict:
    view = dict(doc)
    view["status"] = _payment_request_effective_status(doc, now or datetime.now(timezone.utc))
    return view


async def create_payment_request(user_id: str, payload: PaymentRequestCreate) -> dict:
    db = get_database()
    source = await _get_account_by_user(user_id)
    if source["status"] != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contul tău nu este activ.")

    # Același screening determinist ca la un transfer (vezi
    # content_screening.py) — dar aici BLOCĂM crearea, nu doar avertizăm
    # (vezi comentariul de la PaymentRequestOut din models.py pentru de
    # ce): o cerere de plată e un link/QR menit să fie trimis mai departe,
    # nu o tranzacție privată deja consumată.
    if content_screening.screen_description(payload.description):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Descrierea conține termeni asociați cu activități ilegale/violente — reformuleaz-o ca să poți crea cererea.",
        )

    requester_name = await _get_user_name(user_id)
    now = datetime.now(timezone.utc)

    doc = {
        "requester_user_id": user_id,
        "requester_account_id": source["id"],
        "requester_iban": source["iban"],
        "requester_name": requester_name,
        "amount_minor": payload.amount_minor,
        "currency": source["currency"],
        "description": payload.description,
        "status": "open",
        "created_at": now,
        "expires_at": now + timedelta(days=_PAYMENT_REQUEST_EXPIRY_DAYS),
        "paid_at": None,
        "paid_by_user_id": None,
        "paid_by_name": None,
        "transaction_id": None,
    }
    result = await db.payment_requests.insert_one(doc)
    doc["_id"] = result.inserted_id
    logger.info("transactions-service: cerere de plată creată (id=%s, user_id=%s)", doc["_id"], user_id)
    return _to_payment_request_view(doc, now)


async def list_my_payment_requests(user_id: str) -> list[dict]:
    db = get_database()
    cursor = db.payment_requests.find({"requester_user_id": user_id}).sort("created_at", -1)
    docs = await cursor.to_list(length=200)
    now = datetime.now(timezone.utc)
    return [_to_payment_request_view(doc, now) for doc in docs]


async def _get_payment_request_doc(request_id: str) -> dict:
    db = get_database()
    try:
        object_id = ObjectId(request_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cerere de plată inexistentă.") from exc
    doc = await db.payment_requests.find_one({"_id": object_id})
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cerere de plată inexistentă.")
    return doc


async def get_payment_request(request_id: str, user_id: str) -> dict:
    """Vizualizabilă de ORICE user autentificat, nu doar de cel care a
    creat-o — vezi routers/payment_requests.py (așa poate cineva care a
    primit link-ul să vadă suma/descrierea înainte de a plăti)."""
    doc = await _get_payment_request_doc(request_id)
    return _to_payment_request_view(doc)


async def pay_payment_request(
    request_id: str, user_id: str, background_tasks: BackgroundTasks | None = None
) -> dict:
    db = get_database()
    doc = await _get_payment_request_doc(request_id)
    now = datetime.now(timezone.utc)

    if _payment_request_effective_status(doc, now) != "open":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Această cerere de plată nu mai este activă.")
    if doc["requester_user_id"] == user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nu poți plăti propria cerere de plată.")

    # Claim atomic ÎNAINTE de a muta bani — altfel două plăți concurente pe
    # ACEEAȘI cerere ar putea trece amândouă prin create_transfer (double-
    # spend). Dacă find_one_and_update nu găsește nimic, altcineva a apucat
    # deja cererea (sau a fost anulată chiar acum) — 409, nu se continuă.
    claimed = await db.payment_requests.find_one_and_update(
        {"_id": doc["_id"], "status": "open"},
        {"$set": {"status": "processing"}},
    )
    if claimed is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Această cerere de plată tocmai a fost plătită sau anulată."
        )

    try:
        transfer_payload = TransferRequest(
            to_iban=doc["requester_iban"],
            amount_minor=doc["amount_minor"],
            description=doc["description"] or "Cerere de plată",
        )
        transaction_view = await create_transfer(transfer_payload, user_id, background_tasks)
    except Exception:
        # Revenim la "open" pe orice eșec (ex. sold insuficient) — altfel
        # cererea ar rămâne blocată în "processing" pentru totdeauna, fără
        # ca userul să mai poată reîncerca.
        await db.payment_requests.update_one({"_id": doc["_id"], "status": "processing"}, {"$set": {"status": "open"}})
        raise

    payer_name = await _get_user_name(user_id)
    await db.payment_requests.update_one(
        {"_id": doc["_id"]},
        {
            "$set": {
                "status": "paid",
                "paid_at": now,
                "paid_by_user_id": user_id,
                "paid_by_name": payer_name,
                "transaction_id": ObjectId(transaction_view["_id"]),
            }
        },
    )
    logger.info("transactions-service: cerere de plată achitată (id=%s, plătitor=%s)", doc["_id"], user_id)
    return transaction_view


async def cancel_payment_request(request_id: str, user_id: str) -> dict:
    doc = await _get_payment_request_doc(request_id)
    if doc["requester_user_id"] != user_id:
        # 404, nu 403 — nu confirmăm existența unei cereri a altcuiva.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cerere de plată inexistentă.")

    now = datetime.now(timezone.utc)
    if _payment_request_effective_status(doc, now) != "open":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Această cerere de plată nu mai este activă.")

    db = get_database()
    result = await db.payment_requests.update_one(
        {"_id": doc["_id"], "status": "open"}, {"$set": {"status": "cancelled"}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Această cerere de plată nu mai este activă.")

    doc["status"] = "cancelled"
    logger.info("transactions-service: cerere de plată anulată (id=%s)", doc["_id"])
    return _to_payment_request_view(doc, now)


def _build_filter_query(source_account_id: str, filters: TransactionFilters) -> dict:
    """Construiește filtrul Mongo pentru lista/exportul de tranzacții ale
    userului curent. TOATĂ filtrarea se face aici, în backend — nu doar
    în frontend — astfel încât paginarea și exportul CSV să rămână
    corecte indiferent de câte tranzacții are userul.

    NOTĂ despre `account_id`: MVP-ul are un singur cont per user, deci
    parametrul e validat (trebuie să corespundă contului userului) dar nu
    schimbă practic rezultatul — pregătit arhitectural pentru userii cu
    mai multe conturi, fără să inventăm funcționalitate inexistentă acum.

    NOTĂ despre vizibilitate expeditor/destinatar: expeditorul vede
    ÎNTREGUL istoric al propriilor transferuri, indiferent de status —
    are nevoie să știe ce s-a întâmplat cu banii lui (reținut, eșuat,
    anulat, reușit). Destinatarul vede o tranzacție DOAR după ce chiar a
    ajuns la el (status="completed") — nu are niciun motiv să afle că
    cineva a ÎNCERCAT să-i trimită bani care au fost reținuți pentru
    verificare de fraudă, au eșuat sau au fost anulate; ar dezvălui
    inutil informații despre expeditor și ar crea confuzie fără rost.

    `include_all_statuses` dezactivează exact restricția de mai sus —
    folosit STRICT de personal (routers/staff.py::get_customer_transactions),
    care revizuiește un client și are nevoie de imaginea completă (inclusiv
    încercări primite care n-au ajuns la el — context relevant pentru o
    investigație de fraudă), nu de experiența "curată" a clientului obișnuit.
    """
    if include_all_statuses:
        query: dict = {"$or": [{"from_account_id": source_account_id}, {"to_account_id": source_account_id}]}
    else:
        query = {
            "$or": [
                {"from_account_id": source_account_id},
                {"to_account_id": source_account_id, "status": "completed"},
            ]
        }

    if filters.direction == "outgoing":
        query["from_account_id"] = source_account_id
    elif filters.direction == "incoming":
        query["to_account_id"] = source_account_id
        if not include_all_statuses:
            query["status"] = "completed"

    if filters.category:
        query["category"] = filters.category.strip().lower()

    created_at_range: dict = {}
    if filters.date_from is not None:
        created_at_range["$gte"] = filters.date_from
    if filters.date_to is not None:
        created_at_range["$lte"] = filters.date_to
    if created_at_range:
        query["created_at"] = created_at_range

    amount_range: dict = {}
    if filters.min_amount_minor is not None:
        amount_range["$gte"] = filters.min_amount_minor
    if filters.max_amount_minor is not None:
        amount_range["$lte"] = filters.max_amount_minor
    if amount_range:
        query["amount_minor"] = amount_range

    if filters.search:
        pattern = {"$regex": filters.search.strip(), "$options": "i"}
        query["$and"] = [
            {"$or": [{"description": pattern}, {"from_iban": pattern}, {"to_iban": pattern}]},
        ]

    return query


async def list_transactions_for_user(
    user_id: str, limit: int, skip: int, filters: TransactionFilters | None = None, *, include_all_statuses: bool = False
) -> list[dict]:
    db = get_database()
    source = await _get_account_by_user(user_id)

    if filters is not None and filters.account_id and filters.account_id != source["id"]:
        # Userul nu are acest cont — listă goală, nu eroare (nu dezvăluim
        # dacă account_id aparține altcuiva).
        return []

    query = _build_filter_query(source["id"], filters or TransactionFilters(), include_all_statuses=include_all_statuses)
    cursor = db.transactions.find(query).sort("created_at", -1).skip(skip).limit(limit)
    docs = await cursor.to_list(length=limit)
    return [to_transaction_view(doc, viewer_account_id=source["id"]) for doc in docs]


async def export_transactions_csv(user_id: str, filters: TransactionFilters) -> str:
    """Generează CSV-ul tranzacțiilor FILTRATE ale userului curent — vezi
    _build_filter_query. Nu exportă niciodată tranzacțiile altui user
    (query-ul e mereu legat de contul userului autentificat).
    """
    db = get_database()
    source = await _get_account_by_user(user_id)
    query = _build_filter_query(source["id"], filters)

    docs = await db.transactions.find(query).sort("created_at", -1).to_list(length=10_000)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Data", "Descriere", "Categorie", "Cont/Card", "Directie", "Suma", "Moneda", "Status"])
    for doc in docs:
        view = to_transaction_view(doc, viewer_account_id=source["id"])
        signed_amount = view["amount"] if view["direction"] == "incoming" else f"-{view['amount']}"
        writer.writerow(
            [
                view["created_at"].isoformat(),
                view["description"] or view["counterparty_iban"],
                view["category"],
                "Cont curent RON",
                view["direction"],
                signed_amount,
                view["currency"],
                view["status"],
            ]
        )
    return buffer.getvalue()


async def recognize_transaction(transaction_id: str, user_id: str) -> dict:
    return await _set_transaction_flag(transaction_id, user_id, "recognized", True)


async def report_transaction(transaction_id: str, user_id: str, payload: ReportTransactionRequest) -> dict:
    doc = await _set_transaction_flag(transaction_id, user_id, "reported", True)
    if payload.reason:
        db = get_database()
        await db.transactions.update_one({"_id": ObjectId(transaction_id)}, {"$set": {"report_reason": payload.reason}})
    logger.info("transactions-service: tranzacție raportată (tx_id=%s, user_id=%s)", transaction_id, user_id)
    return doc


async def _set_transaction_flag(transaction_id: str, user_id: str, field: str, value: bool) -> dict:
    db = get_database()
    source = await _get_account_by_user(user_id)

    try:
        object_id = ObjectId(transaction_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID de tranzacție invalid.") from exc

    doc = await db.transactions.find_one({"_id": object_id})
    if doc is None or source["id"] not in (doc["from_account_id"], doc["to_account_id"]):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tranzacția nu există.")

    await db.transactions.update_one({"_id": object_id}, {"$set": {field: value}})
    updated = await db.transactions.find_one({"_id": object_id})
    return to_transaction_view(updated, viewer_account_id=source["id"])


async def get_transaction_for_user(transaction_id: str, user_id: str) -> dict:
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

    # Destinatarul (fără să fie și expeditorul — vezi _build_filter_query
    # pentru motiv) n-are voie să vadă tranzacția înainte să chiar ajungă
    # la el — același 404 "nu există", ca să nu dezvăluim nici măcar că a
    # existat o încercare.
    is_receiver_only = doc["to_account_id"] == source["id"] and doc["from_account_id"] != source["id"]
    if is_receiver_only and doc["status"] != "completed":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tranzacția nu există.")

    return to_transaction_view(doc, viewer_account_id=source["id"])


# --- Analytics (Spending & Forecast) --------------------------------------
#
# Determinist, calculat direct din tx_db — NU folosește AI/ML. Vezi task-ul
# MaestroBank, secțiunea 16: "Spending și Forecast sunt O SINGURĂ PAGINĂ".


def _month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _days_in_month(now: datetime) -> int:
    import calendar

    return calendar.monthrange(now.year, now.month)[1]


async def _get_subscriptions_for_user(user_id: str) -> list[dict]:
    """Abonamentele active ale userului, prin API-ul budgets-service
    (NU citim niciodată direct budgets_db din acest serviciu).

    Degradare grațioasă: dacă budgets-service e indisponibil, forecast-ul
    continuă fără abonamente (mai puțin precis, dar nu blochează pagina).
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.budgets_service_url}/internal/budgets/subscriptions/by-user/{user_id}")
        if response.status_code == 200:
            return response.json()
    except httpx.RequestError:
        logger.warning("transactions-service: budgets-service indisponibil pentru forecast (user_id=%s)", user_id)
    return []


async def get_spending_analytics(user_id: str) -> dict:
    db = get_database()
    source = await _get_account_by_user(user_id)
    now = datetime.now(timezone.utc)
    month_start = _month_start(now)

    docs = await db.transactions.find(
        {
            "from_account_id": source["id"],
            "status": "completed",
            "created_at": {"$gte": month_start, "$lte": now},
        }
    ).to_list(length=10_000)

    totals_by_category: dict[str, int] = {}
    total_spent_minor = 0
    for doc in docs:
        amount = doc["amount_minor"]
        category = doc.get("category", "other")
        totals_by_category[category] = totals_by_category.get(category, 0) + amount
        total_spent_minor += amount

    days_elapsed = max((now - month_start).days + 1, 1)
    average_daily_spending_minor = round(total_spent_minor / days_elapsed)

    by_category = [
        {
            "category": category,
            "amount_minor": amount,
            "percentage": round((amount / total_spent_minor) * 100, 1) if total_spent_minor > 0 else 0,
        }
        for category, amount in sorted(totals_by_category.items(), key=lambda item: item[1], reverse=True)
    ]

    return {
        "month": month_start.strftime("%Y-%m"),
        "total_spent_minor": total_spent_minor,
        "average_daily_spending_minor": average_daily_spending_minor,
        "by_category": by_category,
    }


async def get_cash_flow_analytics(user_id: str, days: int = 30) -> dict:
    db = get_database()
    source = await _get_account_by_user(user_id)
    now = datetime.now(timezone.utc)
    range_start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)

    docs = await db.transactions.find(
        {
            "$or": [{"from_account_id": source["id"]}, {"to_account_id": source["id"]}],
            "status": "completed",
            "created_at": {"$gte": range_start},
        }
    ).to_list(length=10_000)

    daily: dict[str, dict[str, int]] = {}
    for offset in range(days):
        day_key = (range_start + timedelta(days=offset)).strftime("%Y-%m-%d")
        daily[day_key] = {"incoming_minor": 0, "outgoing_minor": 0}

    for doc in docs:
        day_key = doc["created_at"].strftime("%Y-%m-%d")
        if day_key not in daily:
            continue
        if doc["from_account_id"] == source["id"]:
            daily[day_key]["outgoing_minor"] += doc["amount_minor"]
        else:
            daily[day_key]["incoming_minor"] += doc["amount_minor"]

    points = [
        {
            "date": day_key,
            "incoming_minor": values["incoming_minor"],
            "outgoing_minor": values["outgoing_minor"],
            "net_minor": values["incoming_minor"] - values["outgoing_minor"],
        }
        for day_key, values in sorted(daily.items())
    ]

    return {"period_days": days, "points": points}


async def get_forecast_analytics(user_id: str) -> dict:
    now = datetime.now(timezone.utc)
    account = await _get_account_by_user(user_id)
    spending = await get_spending_analytics(user_id)
    subscriptions = await _get_subscriptions_for_user(user_id)

    days_total = _days_in_month(now)
    days_remaining = max(days_total - now.day, 0)
    projected_variable_spending_minor = spending["average_daily_spending_minor"] * days_remaining

    upcoming_obligations = [
        {
            "name": sub["name"],
            "amount_minor": sub["amount_minor"],
            "billing_day": sub["billing_day"],
        }
        for sub in subscriptions
        if sub.get("active", True) and sub.get("billing_day", 0) >= now.day
    ]
    upcoming_obligations_minor = sum(item["amount_minor"] for item in upcoming_obligations)

    expected_expenses_minor = projected_variable_spending_minor + upcoming_obligations_minor
    estimated_end_of_month_balance_minor = account["balance_minor"] - expected_expenses_minor

    return {
        "current_balance_minor": account["balance_minor"],
        "expected_expenses_minor": expected_expenses_minor,
        "upcoming_obligations": upcoming_obligations,
        "estimated_end_of_month_balance_minor": estimated_end_of_month_balance_minor,
        "days_remaining_in_month": days_remaining,
    }
