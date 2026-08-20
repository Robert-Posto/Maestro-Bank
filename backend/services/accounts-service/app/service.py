"""Logica de business a accounts-service.

Separată de routing (`app/routers/accounts.py` pentru rutele protejate
JWT, `app/routers/internal.py` pentru rutele service-to-service) și de
modele (`app/models.py`). Acest modul e singurul care atinge
`db.accounts` / `db.cards` direct.
"""

import logging
import random
from datetime import datetime, timezone

import httpx
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status

from app.config import settings
from app.database import get_database
from app.iban_service import generate_unique_demo_iban
from app.money import format_minor_amount
from app.models import (
    AccountPublicOut,
    BeneficiaryCreate,
    CardCreateRequest,
    CardLimitUpdate,
    CardRevealRequest,
    CardSettingsUpdate,
    CreatableAccountType,
    InternalAccountView,
    InternalTransferResponse,
)

logger = logging.getLogger("accounts-service")

_DEMO_CARD_TYPE = "virtual"
_DEMO_CARD_VALID_YEARS = 3
_DEMO_PAN_BIN = "4111"  # prefix demo (Visa test BIN) — NU e un card real, doar plauzibil vizual

# Emitere card nou (Cardul meu) ---------------------------------------------
_PHYSICAL_CARD_FEE_MINOR = 2_000  # 20,00 RON, dedusă din cont la emiterea unui card fizic
_MAX_CARDS_PER_USER = 6  # cap defensiv demo — evită creare nelimitată de carduri


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
        account_type=account.get("account_type", "current"),
        verification_document_name=account.get("verification_document_name"),
    )


def _to_internal_view(account: dict) -> InternalAccountView:
    return InternalAccountView(
        id=str(account["_id"]),
        user_id=account["user_id"],
        iban=account["iban"],
        currency=account["currency"],
        balance_minor=account["balance_minor"],
        status=account["status"],
        account_type=account.get("account_type", "current"),
    )


def _generate_demo_pan() -> str:
    """PAN demo, 16 cifre, cu prefix plauzibil vizual (BIN de test) — NU e
    un card real, nu trece prin niciun procesator de plăți."""
    remaining = "".join(str(random.randint(0, 9)) for _ in range(16 - len(_DEMO_PAN_BIN)))
    return f"{_DEMO_PAN_BIN}{remaining}"


def _generate_demo_cvv() -> str:
    return f"{random.randint(0, 999):03d}"


def _demo_expiry() -> tuple[int, int]:
    now = datetime.now(timezone.utc)
    return now.month, now.year + _DEMO_CARD_VALID_YEARS


async def _ensure_card_secrets(card: dict) -> dict:
    """Backfill lazy pentru `pan`/`cvv` la carduri create ÎNAINTE de introducerea
    reveal-ului (Cardul meu) — la fel ca la celelalte controale de card, lipsa
    câmpurilor în Mongo nu cere o migrare de date explicită, doar se completează
    la prima accesare și se persistă, ca reveal-urile ulterioare să fie stabile."""
    if "pan" in card and "cvv" in card:
        return card

    pan = card.get("pan") or f"{_DEMO_PAN_BIN}{'0' * (12 - len(card['last_four']))}{card['last_four']}"
    cvv = card.get("cvv") or _generate_demo_cvv()

    db = get_database()
    await db.cards.update_one({"_id": card["_id"]}, {"$set": {"pan": pan, "cvv": cvv}})
    return {**card, "pan": pan, "cvv": cvv}


# --- rute protejate JWT (app/routers/accounts.py) -------------------------


async def get_account_for_user(user_id: str) -> dict:
    """Rezolvă STRICT contul curent ("current") al userului.

    Filtrăm explicit după `account_type` — de când un user poate avea mai
    multe conturi (economii/depozit/student, vezi create_additional_account),
    un `find_one({"user_id": ...})` fără filtru ar fi ambiguu (Mongo nu
    garantează care document îl întoarce). Toate fluxurile existente
    (emitere card, dev/fund, sursa unui transfer) trebuie să rămână legate
    STRICT de contul curent — cel puțin până când Transferurile vor putea
    alege explicit contul sursă.
    """
    db = get_database()
    account = await db.accounts.find_one({"user_id": user_id, "account_type": "current"})
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nu există niciun cont pentru acest utilizator.",
        )
    return account


async def backfill_missing_account_types() -> None:
    """Migrare idempotentă, rulată la fiecare pornire (vezi main.py::lifespan).

    Conturile create ÎNAINTE de introducerea `account_type` nu au acest
    câmp în Mongo deloc — și un filtru de query `{"account_type": "current"}`
    NU se potrivește cu un document unde câmpul lipsește (spre deosebire de
    citirea prin Pydantic, unde lipsa cade automat pe default). Fără acest
    backfill, TOATE conturile existente (inclusiv userii demo din
    scripts/seed_demo_data.py) ar deveni brusc "invizibile" pentru
    get_account_for_user/get_account_by_user -> transferuri, emitere card,
    dev/fund ar întoarce 404. Rulăm asta o dată la boot, cost neglijabil
    (un singur update_many, afectează 0 documente după prima rulare).
    """
    db = get_database()
    result = await db.accounts.update_many(
        {"account_type": {"$exists": False}},
        {"$set": {"account_type": "current"}},
    )
    if result.modified_count:
        logger.info("accounts-service: backfill account_type=current aplicat pe %s conturi vechi", result.modified_count)


async def list_accounts_for_user(user_id: str) -> list[dict]:
    """Toate conturile userului (curent + economii/depozit/student), cel mai vechi primul."""
    db = get_database()
    cursor = db.accounts.find({"user_id": user_id}).sort("created_at", 1)
    return await cursor.to_list(length=10)


_MAX_ACCOUNTS_PER_USER = 4  # current + savings + deposit + student — suficient pentru acest demo

_ACCOUNT_TYPE_LABELS: dict[str, str] = {
    "savings": "economii",
    "deposit": "depozit",
    "student": "student",
}


async def create_additional_account(
    user_id: str, account_type: CreatableAccountType, document_filename: str | None = None
) -> AccountPublicOut:
    """Deschide un cont suplimentar (economii/depozit/student) pentru userul curent.

    Maxim UN cont per tip, per user — evită duplicate fără sens într-un
    demo unde oricum nu există un motiv real să ai două conturi de economii.
    Pentru "student", `document_filename` a fost deja validat ca fiind
    prezent de AccountCreateRequest — aici doar îl persistăm (metadata,
    nu conținutul fișierului, vezi nota din models.py).
    """
    db = get_database()

    existing = await db.accounts.find_one({"user_id": user_id, "account_type": account_type})
    if existing is not None:
        label = _ACCOUNT_TYPE_LABELS.get(account_type, account_type)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ai deja un cont de {label}.",
        )

    total = await db.accounts.count_documents({"user_id": user_id})
    if total >= _MAX_ACCOUNTS_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ai atins numărul maxim de conturi ({_MAX_ACCOUNTS_PER_USER}).",
        )

    iban = await generate_unique_demo_iban(db)
    now = datetime.now(timezone.utc)
    account_doc = {
        "user_id": user_id,
        "iban": iban,
        "currency": "RON",
        "balance_minor": 0,
        "status": "active",
        "account_type": account_type,
        "verification_document_name": document_filename,
        "created_at": now,
    }
    result = await db.accounts.insert_one(account_doc)
    logger.info(
        "accounts-service: cont suplimentar deschis (user_id=%s, account_id=%s, type=%s, iban=%s, document=%s)",
        user_id,
        result.inserted_id,
        account_type,
        iban,
        bool(document_filename),
    )
    created = await db.accounts.find_one({"_id": result.inserted_id})
    return to_public_account(created)


async def delete_account(user_id: str, account_id: str) -> None:
    """Închide un cont suplimentar (economii/depozit/student) — NICIODATĂ contul curent.

    Reguli, ca la orice bancă reală:
      - contul curent nu poate fi șters (e sursa tuturor transferurilor și
        a cardurilor — vezi get_account_for_user);
      - contul trebuie golit înainte (balance_minor == 0) — userul își
        transferă soldul rămas către alt cont al lui, prin Transferuri,
        folosind IBAN-ul propriu (deja posibil, vezi Transfers feature).
    """
    db = get_database()
    try:
        object_id = ObjectId(account_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID de cont invalid.") from exc

    account = await db.accounts.find_one({"_id": object_id})
    if account is None or account["user_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contul nu există.")

    if account.get("account_type", "current") == "current":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contul curent nu poate fi șters.",
        )

    if account["balance_minor"] != 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Golește mai întâi contul (transferă soldul rămas) înainte să-l ștergi.",
        )

    await db.accounts.delete_one({"_id": object_id})
    logger.info("accounts-service: cont șters (user_id=%s, account_id=%s, type=%s)", user_id, object_id, account.get("account_type"))


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


async def create_card(user_id: str, payload: CardCreateRequest) -> dict:
    """Emite un card nou pentru contul userului curent (design + virtual/fizic
    + opțional unică folosință, ca la Revolut). Cardurile fizice presupun o
    taxă de emitere dedusă atomic din cont — vezi _PHYSICAL_CARD_FEE_MINOR."""
    db = get_database()
    account = await get_account_for_user(user_id)

    existing_count = await db.cards.count_documents({"user_id": user_id})
    if existing_count >= _MAX_CARDS_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ai atins numărul maxim de carduri ({_MAX_CARDS_PER_USER}).",
        )

    if payload.type == "physical":
        debit_result = await db.accounts.update_one(
            {"_id": account["_id"], "balance_minor": {"$gte": _PHYSICAL_CARD_FEE_MINOR}},
            {"$inc": {"balance_minor": -_PHYSICAL_CARD_FEE_MINOR}},
        )
        if debit_result.modified_count != 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Sold insuficient pentru taxa de emitere a cardului fizic "
                f"({format_minor_amount(_PHYSICAL_CARD_FEE_MINOR)} RON).",
            )

    expiry_month, expiry_year = _demo_expiry()
    pan = _generate_demo_pan()
    now = datetime.now(timezone.utc)
    card_doc = {
        "user_id": user_id,
        "account_id": account["_id"],
        "pan": pan,
        "last_four": pan[-4:],
        "cvv": _generate_demo_cvv(),
        "expiry_month": expiry_month,
        "expiry_year": expiry_year,
        "status": "active",
        "type": payload.type,
        "design": payload.design,
        "is_one_time": payload.is_one_time,
        "created_at": now,
        "is_frozen": False,
        "online_payments_enabled": True,
        "contactless_enabled": True,
        "atm_withdrawals_enabled": True,
        "international_payments_enabled": True,
        "daily_limit_minor": 500_000,
    }
    card_result = await db.cards.insert_one(card_doc)
    logger.info(
        "accounts-service: card nou emis (user_id=%s, card_id=%s, type=%s, design=%s, is_one_time=%s)",
        user_id,
        card_result.inserted_id,
        payload.type,
        payload.design,
        payload.is_one_time,
    )
    return await db.cards.find_one({"_id": card_result.inserted_id})


async def _verify_password_with_auth_service(user_id: str, password: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{settings.auth_service_url}/internal/auth/verify-password",
                json={"user_id": user_id, "password": password},
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("accounts-service: verificarea parolei a eșuat (user_id=%s): %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Nu am putut verifica parola — serviciul de autentificare este indisponibil.",
        ) from exc

    return bool(response.json().get("valid", False))


async def _verify_webauthn_with_auth_service(user_id: str, card_id: str, challenge_id: str, assertion: dict) -> bool:
    """`card_id` e valoarea REZOLVATĂ server-side (din _get_card_for_user,
    apelat înainte de asta în reveal_card) — niciodată una trimisă de
    client — ca action_payload din challenge-ul de step-up. Astfel un
    assertion capturat pentru cardul A nu poate fi refolosit ca să
    dezvăluie cardul B, chiar dacă atacatorul ar reuși să retrimită
    challenge_id + assertion neschimbate."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{settings.auth_service_url}/internal/auth/verify-webauthn",
                json={
                    "user_id": user_id,
                    "challenge_id": challenge_id,
                    "action": "card_reveal",
                    "action_payload": card_id,
                    "credential": assertion,
                },
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("accounts-service: verificarea passkey-ului a eșuat (user_id=%s): %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Nu am putut verifica passkey-ul — serviciul de autentificare este indisponibil.",
        ) from exc

    return bool(response.json().get("valid", False))


async def reveal_card(card_id: str, user_id: str, payload: CardRevealRequest) -> dict:
    """Dezvăluie PAN + CVV pentru un card — DOAR după reconfirmarea
    identității userului (parolă SAU passkey, vezi CardRevealRequest).
    Acțiune sensibilă: nu se bazează doar pe JWT (care poate rămâne valid
    ore întregi), la fel ca la orice bancă reală care cere reautentificare
    pentru date de card."""
    card = await _get_card_for_user(card_id, user_id)

    if payload.password is not None:
        ok = await _verify_password_with_auth_service(user_id, payload.password)
        error_detail = "Parolă incorectă."
    else:
        ok = await _verify_webauthn_with_auth_service(
            user_id, card_id, payload.webauthn_challenge_id, payload.webauthn_assertion
        )
        error_detail = "Confirmarea biometrică a eșuat."

    if not ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error_detail)

    card = await _ensure_card_secrets(card)
    return {
        "pan": card["pan"],
        "cvv": card["cvv"],
        "expiry_month": card["expiry_month"],
        "expiry_year": card["expiry_year"],
    }


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
        "account_type": "current",
        "created_at": now,
    }
    account_result = await db.accounts.insert_one(account_doc)

    expiry_month, expiry_year = _demo_expiry()
    pan = _generate_demo_pan()
    card_doc = {
        "user_id": user_id,
        "account_id": account_result.inserted_id,
        "pan": pan,
        "last_four": pan[-4:],
        "cvv": _generate_demo_cvv(),
        "expiry_month": expiry_month,
        "expiry_year": expiry_year,
        "status": "active",
        "type": _DEMO_CARD_TYPE,
        "design": "midnight",
        "is_one_time": False,
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
    """Folosit de transactions-service pentru a determina contul SURSĂ al userului autentificat.

    Filtrat strict pe "current" — vezi nota din get_account_for_user. Sursa
    unui transfer rămâne mereu contul curent, chiar dacă userul are și
    conturi de economii/depozit/student.
    """
    db = get_database()
    account = await db.accounts.find_one({"user_id": user_id, "account_type": "current"})
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
