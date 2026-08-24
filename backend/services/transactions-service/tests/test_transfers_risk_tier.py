"""Teste de integrare pentru câmpul `risk` prin fluxul REAL de transfer
(POST /transactions/transfers) — fișier auto-conținut, la fel ca
test_transfers_fraud.py.

Notă de infrastructură IMPORTANTĂ: cu `httpx.AsyncClient(transport=
ASGITransport(app=app))`, `BackgroundTasks` rulează ÎNAINTE ca
`await client.post(...)` să întoarcă rezultatul (Starlette le așteaptă ca
parte din același ciclu ASGI, în-proces) — deci aceste teste pot verifica
scrierile lui Guardian imediat după POST, fără nicio așteptare/sleep.

"step_up" (60-79) nu e reprodus separat aici prin fluxul HTTP real — la un
user cold-start, fără cohortă/istoric seedate, doar AMT-03/AMT-04/BEN-01/
BEH-01 se pot declanșa determinist (restul au nevoie de date care nu
există într-un test izolat), ceea ce landează fie pe "notify" (~50), fie
pe "hold" (~82) — nu pe intervalul 60-79. Mapping-ul pur pentru "step_up"
e deja acoperit exact în test_guardian_service.py::test_compute_customer_
risk_step_up_band_is_pending — codul care-l tratează e IDENTIC cu cel
pentru "notify" (aceeași ramură `_CUSTOMER_PHRASE_BANDS`), deci "notify"
aici demonstrează exact aceeași cablare.
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import get_database
from app.guardian import service as guardian_service
from app.main import app

pytestmark = pytest.mark.asyncio

USER_ID = str(ObjectId())
SOURCE_ACCOUNT_ID = str(ObjectId())
DEST_ACCOUNT_ID = str(ObjectId())

SOURCE_ACCOUNT = {
    "id": SOURCE_ACCOUNT_ID,
    "user_id": USER_ID,
    "iban": "RO11MAES0000000000000001",
    "currency": "RON",
    "balance_minor": 100_000,
    "status": "active",
}

DEST_ACCOUNT = {
    "id": DEST_ACCOUNT_ID,
    "user_id": str(ObjectId()),
    "iban": "RO22MAES0000000000000002",
    "currency": "RON",
    "balance_minor": 0,
    "status": "active",
}


def _make_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "email": "test@example.com", "iat": now, "exp": now + timedelta(minutes=5)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


AUTH_HEADER = {"Authorization": f"Bearer {_make_token(USER_ID)}"}


@pytest.fixture(autouse=True)
async def clean_transactions():
    await get_database().transactions.delete_many({})
    yield
    await get_database().transactions.delete_many({})


HOLDING_ACCOUNT_ID = str(ObjectId())


@pytest.fixture
def mock_accounts(monkeypatch):
    """Mock-uiește ATÂT calea non-hold (app.service._apply_transfer) CÂT ȘI
    calea de reținere (app.holds._resolve_holding_account_id/_apply_ledger_
    transfer/_fetch_user_contact) — vezi test_transfers_hold_integration.py,
    aceeași convenție. Fără al doilea set, un scenariu "hold" ar încerca
    apeluri HTTP REALE către accounts-service pentru conturi care nu există
    acolo (ID-uri fictive, doar din acest fișier de test)."""
    state = {"source": dict(SOURCE_ACCOUNT), "destination": dict(DEST_ACCOUNT), "holding_balance_minor": 0}

    async def fake_get_by_user(user_id: str) -> dict:
        return state["source"]

    async def fake_get_by_iban(iban: str):
        return state["destination"]

    async def fake_apply_transfer(from_id: str, to_id: str, amount_minor: int) -> dict:
        state["source"]["balance_minor"] -= amount_minor
        state["destination"]["balance_minor"] += amount_minor
        return {
            "from_balance_minor": state["source"]["balance_minor"],
            "to_balance_minor": state["destination"]["balance_minor"],
        }

    async def fake_get_user_name(user_id: str) -> str | None:
        return None

    async def fake_resolve_holding_account_id() -> str:
        return HOLDING_ACCOUNT_ID

    async def fake_apply_ledger_transfer(from_account_id: str, to_account_id: str, amount_minor: int) -> bool:
        if from_account_id == state["source"]["id"]:
            if state["source"]["balance_minor"] < amount_minor:
                return False
            state["source"]["balance_minor"] -= amount_minor
            state["holding_balance_minor"] += amount_minor
            return True
        if from_account_id == HOLDING_ACCOUNT_ID:
            if state["holding_balance_minor"] < amount_minor:
                return False
            state["holding_balance_minor"] -= amount_minor
            if to_account_id == state["destination"]["id"]:
                state["destination"]["balance_minor"] += amount_minor
            elif to_account_id == state["source"]["id"]:
                state["source"]["balance_minor"] += amount_minor
            return True
        return False

    async def fake_fetch_user_contact(user_id: str) -> dict:
        return {"first_name": "Test", "last_name": "User", "email": "test@example.com", "phone_number": "+40700000000"}

    monkeypatch.setattr("app.service._get_account_by_user", fake_get_by_user)
    monkeypatch.setattr("app.service._get_account_by_iban", fake_get_by_iban)
    monkeypatch.setattr("app.service._apply_transfer", fake_apply_transfer)
    monkeypatch.setattr("app.service._get_user_name", fake_get_user_name)
    monkeypatch.setattr("app.holds._resolve_holding_account_id", fake_resolve_holding_account_id)
    monkeypatch.setattr("app.holds._apply_ledger_transfer", fake_apply_ledger_transfer)
    monkeypatch.setattr("app.holds._fetch_user_contact", fake_fetch_user_contact)
    return state


@pytest.fixture
def guardian_task_spy(monkeypatch):
    calls: list[dict] = []
    real = guardian_service.generate_guardian_explanations

    async def spy(*, transaction_id, user_id):
        calls.append({"transaction_id": transaction_id, "user_id": user_id})
        await real(transaction_id=transaction_id, user_id=user_id)

    monkeypatch.setattr("app.guardian.service.generate_guardian_explanations", spy)
    return calls


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _seed_established_profile() -> None:
    """Un user cold-start declanșează necondiționat BEN-01+BEH-01 (30 —
    exact pragul "notify") la prima tranzacție, iar VEL-02 e trivial de
    declanșat cu istoric puțin (media zilnică calculată pe fereastra fixă
    de 30 zile e minusculă cu doar 1-2 eșantioane) — "pass" e efectiv
    inatins printr-un transfer live izolat. Seedăm direct un profil STABIL
    (>=20 tranzacții, cerința cold_start_min_transactions) ca tranzacția
    evaluată în test să nu declanșeze NIMIC — la fel ca datele reale produse
    de scripts/seed_fraud_scenarios.py pentru scenariile "normale"."""
    db = get_database()
    now = datetime.now(timezone.utc)
    # Ore alternate 0/23 -> percentile 5/95 acoperă TOATĂ ziua, indiferent
    # la ce oră rulează testul efectiv (fără flakiness legată de ceas).
    history_samples = [
        {"amount_minor": 500, "category": "shopping", "hour_utc": 0 if i % 2 == 0 else 23, "created_at": now - timedelta(days=i + 1)}
        for i in range(25)
    ]
    await db.fraud_profiles.insert_one(
        {
            "user_id": USER_ID,
            "transaction_count": 25,
            "first_transaction_at": now - timedelta(days=25),
            "last_transaction_at": now - timedelta(days=1),
            "history_samples": history_samples,
            "category_counts": {"shopping": 25},
            "beneficiary_countries": ["RO"],
            "created_at": now - timedelta(days=25),
            "updated_at": now - timedelta(days=1),
        }
    )
    # BEN-01 (prima plată) verifică direct tx_db.transactions, nu profilul —
    # are nevoie de o tranzacție PRIOR reală către același IBAN.
    await db.transactions.insert_one(
        {
            "from_account_id": SOURCE_ACCOUNT_ID,
            "to_account_id": DEST_ACCOUNT_ID,
            "from_iban": SOURCE_ACCOUNT["iban"],
            "to_iban": DEST_ACCOUNT["iban"],
            "amount_minor": 500,
            "currency": "RON",
            "description": "",
            "category": "shopping",
            "type": "transfer",
            "status": "completed",
            "recognized": False,
            "reported": False,
            "created_at": now - timedelta(days=1),
        }
    )


async def test_pass_band_is_safe_and_schedules_no_background_task(client: AsyncClient, mock_accounts, guardian_task_spy):
    await _seed_established_profile()

    response = await client.post(
        "/transactions/transfers",
        json={"to_iban": DEST_ACCOUNT["iban"], "amount_minor": 500, "description": "", "category": "shopping"},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["risk"]["tier"] == "safe"
    assert body["risk"]["status"] == "ready"
    assert body["risk"]["phrase"]  # frază fixă, nevidă
    assert guardian_task_spy == []


async def test_notify_band_sets_pending_tier_and_schedules_background_task(
    client: AsyncClient, mock_accounts, guardian_task_spy
):
    # 0.8 x sold -> declanșează AMT-03 (>0.7) dar NU AMT-04 (<0.98) — vezi
    # docstring-ul fișierului pentru de ce landează pe "notify", nu "step_up".
    response = await client.post(
        "/transactions/transfers",
        json={"to_iban": DEST_ACCOUNT["iban"], "amount_minor": 80_000, "description": "", "category": "shopping"},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 201
    body = response.json()

    # Corpul răspunsului reflectă starea SINCRONĂ (tier pending, phrase None
    # la momentul return-ului din create_transfer) — vezi nota din docstring:
    # BackgroundTasks rulează DUPĂ ce view-ul e construit, dar ÎNAINTE ca
    # `await client.post(...)` să întoarcă rezultatul.
    assert body["risk"]["tier"] == "unusual"
    assert len(guardian_task_spy) == 1
    assert guardian_task_spy[0]["user_id"] == USER_ID

    # După ce background task-ul a rulat (garantat, sub ASGITransport),
    # baza de date reflectă rezultatul final.
    evaluation = await get_database().fraud_evaluations.find_one({"transaction_id": ObjectId(body["id"])})
    assert evaluation["guardian"]["status"] in ("ready", "template_fallback")
    assert evaluation["guardian"]["customer_phrase"]
    assert evaluation["guardian"]["staff_explanation"]

    transaction = await get_database().transactions.find_one({"_id": ObjectId(body["id"])})
    assert transaction["risk"]["status"] in ("ready", "template_fallback")
    assert transaction["risk"]["phrase"]


async def test_hold_band_with_real_enforcement_is_held_synchronously(
    client: AsyncClient, mock_accounts, guardian_task_spy
):
    # 0.99 x sold -> AMT-03 + AMT-04 + BEN-01 + BEH-01 -> scor >= 80 -> hold.
    response = await client.post(
        "/transactions/transfers",
        json={"to_iban": DEST_ACCOUNT["iban"], "amount_minor": 99_000, "description": "", "category": "shopping"},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending_review"
    assert body["risk"] == {"tier": "held", "phrase": body["risk"]["phrase"], "status": "ready"}

    # Personalul primește un raport (bandă "hold" e în guardian_staff_report_bands implicit).
    assert len(guardian_task_spy) == 1
    evaluation = await get_database().fraud_evaluations.find_one({"transaction_id": ObjectId(body["id"])})
    assert evaluation["guardian"]["staff_explanation"]

    # risk-ul rămâne EXACT cel setat sincron — Guardian nu-l atinge la hold real.
    transaction = await get_database().transactions.find_one({"_id": ObjectId(body["id"])})
    assert transaction["risk"] == body["risk"]


async def test_hold_band_under_shadow_mode_does_not_claim_held(
    client: AsyncClient, mock_accounts, guardian_task_spy, monkeypatch
):
    """Reconciliere shadow mode: scorul atinge banda "hold", dar
    fraud_shadow_mode=True suprimă aplicarea reală — clientul NU trebuie să
    vadă "held" (nimic n-a fost reținut cu adevărat)."""
    monkeypatch.setattr("app.config.settings.fraud_shadow_mode", True)

    response = await client.post(
        "/transactions/transfers",
        json={"to_iban": DEST_ACCOUNT["iban"], "amount_minor": 99_000, "description": "", "category": "shopping"},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"  # NU a fost reținut cu adevărat
    assert body["risk"]["tier"] == "potentially_dangerous"
    assert body["risk"]["tier"] != "held"
