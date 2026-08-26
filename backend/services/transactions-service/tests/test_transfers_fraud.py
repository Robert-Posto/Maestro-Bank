"""Teste de integrare pentru motorul de fraud, prin fluxul REAL de transfer
(POST /transactions/transfers) — vezi conftest.py `mocking` la fel ca
test_transfers.py (fixtures proprii aici, fișier auto-conținut, ca restul
suitei — vezi nota din test_transfers.py despre de ce apelurile către
accounts-service/auth-service sunt mock-uite acolo unde nu sunt ținta
testului).

Cel mai important test de aici e `test_fraud_evaluation_failure_does_not_
break_transfer` — probează garanția "shadow mode nu poate NICIODATĂ strica
un transfer", nu doar în teorie, ci sub un eșec REAL al motorului.
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import get_database
from app.fraud import context
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


@pytest.fixture
def mock_accounts(monkeypatch):
    state = {"source": dict(SOURCE_ACCOUNT), "destination": dict(DEST_ACCOUNT)}

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

    monkeypatch.setattr("app.service._get_account_by_user", fake_get_by_user)
    monkeypatch.setattr("app.service._get_account_by_iban", fake_get_by_iban)
    monkeypatch.setattr("app.service._apply_transfer", fake_apply_transfer)
    monkeypatch.setattr("app.service._get_user_name", fake_get_user_name)
    return state


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _get_evaluation(transaction_id: str) -> dict | None:
    return await get_database().fraud_evaluations.find_one({"transaction_id": ObjectId(transaction_id)})


async def test_shadow_mode_high_score_does_not_alter_transfer_outcome(client: AsyncClient, mock_accounts, monkeypatch):
    """Sold 100.000: burst VEL-01 + transfer de 99.000 -> AMT-04 (golire
    cont, familia "amount") + BEN-01 (primul beneficiar) + BEH-01 (categorie
    nouă) + VEL-01 (burst) garantează un scor >= 80 ("hold"). AMT-03 nu mai
    contribuie separat (subsumată de AMT-04, vezi catalogue.py::SUBSUMED_BY)
    — vezi test_transfers_hold_integration.py::_trigger_hold pentru de ce
    burst-ul e necesar și de ce IBAN-ul/categoria lui diferă de declanșator.
    Cu shadow mode ACTIV explicit (implicit e False de la faza "PENDING
    hold" — vezi test_transfers_hold_integration.py pentru cazul opus,
    aplicare reală), transferul TOT trebuie să treacă normal — shadow mode
    nu blochează niciodată."""
    monkeypatch.setattr("app.config.settings.fraud_shadow_mode", True)
    for _ in range(5):
        burst = await client.post(
            "/transactions/transfers",
            json={"to_iban": "RO99BURST0000000000000099", "amount_minor": 100, "description": "", "category": "other"},
            headers=AUTH_HEADER,
        )
        assert burst.status_code == 201

    response = await client.post(
        "/transactions/transfers",
        json={"to_iban": DEST_ACCOUNT["iban"], "amount_minor": 99_000, "description": "", "category": "groceries"},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert body["amount_minor"] == 99_000
    # 100_000 - 500 (5 x burst) - 99_000 (declanșator) — toate aplicate normal (shadow mode)
    assert mock_accounts["source"]["balance_minor"] == 500

    evaluation = await _get_evaluation(body["id"])
    assert evaluation is not None
    assert evaluation["status"] == "ok"
    assert evaluation["score"] >= 80
    assert evaluation["decision_would_apply"] == "hold"
    assert evaluation["shadow_mode"] is True
    assert evaluation["ruleset_version"]


async def test_shadow_mode_low_score_transfer_also_unaffected(client: AsyncClient, mock_accounts):
    """Un transfer "banal" (sumă mică, sub orice prag) trebuie să reușească
    la fel — și tot trebuie să lase o înregistrare de audit, chiar la scor 0."""
    response = await client.post(
        "/transactions/transfers",
        json={"to_iban": DEST_ACCOUNT["iban"], "amount_minor": 1_000, "description": ""},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 201
    evaluation = await _get_evaluation(response.json()["id"])
    assert evaluation is not None
    assert evaluation["status"] == "ok"


async def test_fraud_evaluation_failure_does_not_break_transfer(client: AsyncClient, mock_accounts, monkeypatch):
    """CEL MAI IMPORTANT test din acest fișier — probează garanția
    "shadow mode nu poate NICIODATĂ strica un transfer" sub un eșec REAL al
    motorului (nu doar teoretic): build_rule_context aruncă o excepție,
    transferul tot trebuie să reușească, iar o înregistrare DEGRADATĂ
    (status="evaluation_error") tot trebuie scrisă — dreptul la explicație
    nu are voie să aibă o gaură exact acolo unde ceva a mers prost."""

    async def boom(**kwargs):
        raise RuntimeError("eroare simulată în construirea contextului")

    monkeypatch.setattr("app.fraud.context.build_rule_context", boom)

    response = await client.post(
        "/transactions/transfers",
        json={"to_iban": DEST_ACCOUNT["iban"], "amount_minor": 10_000, "description": ""},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert mock_accounts["source"]["balance_minor"] == 90_000  # transferul CHIAR s-a aplicat

    evaluation = await _get_evaluation(body["id"])
    assert evaluation is not None
    assert evaluation["status"] == "evaluation_error"
    assert evaluation["score"] is None
    assert evaluation["decision_would_apply"] is None
    assert "eroare simulată" in evaluation["error"]


async def test_fraud_audit_write_failure_still_completes_transfer_and_logs(
    client: AsyncClient, mock_accounts, monkeypatch, caplog
):
    """Variantă de dublu eșec: scorarea reușește normal, dar SCRIEREA în
    fraud_evaluations eșuează și ea — transferul tot trebuie să reușească,
    iar înregistrarea completă trebuie să ajungă în log (singura plasă de
    siguranță rămasă, fără outbox/WAL — vezi audit.py)."""

    class _FailingCollection:
        async def insert_one(self, doc):
            raise RuntimeError("eroare simulată de scriere Mongo")

    class _FailingDatabase:
        fraud_evaluations = _FailingCollection()

    monkeypatch.setattr("app.fraud.audit.get_database", lambda: _FailingDatabase())

    with caplog.at_level("ERROR", logger="transactions-service"):
        response = await client.post(
            "/transactions/transfers",
            json={"to_iban": DEST_ACCOUNT["iban"], "amount_minor": 10_000, "description": ""},
            headers=AUTH_HEADER,
        )

    assert response.status_code == 201
    assert response.json()["status"] == "completed"
    assert any("scriere audit EȘUATĂ" in record.getMessage() for record in caplog.records)


async def test_fraud_engine_disabled_short_circuits_to_noop(client: AsyncClient, mock_accounts, monkeypatch):
    """Comutatorul operațional FRAUD_ENGINE_ENABLED=false -> transferul
    reușește identic, dar NU se scrie nicio înregistrare de audit."""
    monkeypatch.setattr("app.config.settings.fraud_engine_enabled", False)

    response = await client.post(
        "/transactions/transfers",
        json={"to_iban": DEST_ACCOUNT["iban"], "amount_minor": 99_000, "description": ""},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 201
    assert response.json()["status"] == "completed"
    assert await _get_evaluation(response.json()["id"]) is None


async def test_customer_endpoint_never_leaks_guardian_staff_explanation(client: AsyncClient, mock_accounts):
    """Vezi app/guardian/ — guardian.staff_explanation trăiește STRICT pe
    fraud_evaluations și nu are voie să ajungă NICIODATĂ la client, pe
    NICIUN endpoint orientat spre client (nu doar câmpurile "cunoscute" —
    căutare pe tot corpul JSON, ca să prindă și o eventuală scăpare
    viitoare, nu doar bug-ul de azi)."""
    db = get_database()
    tx_id = ObjectId()
    marker = "SECRET-STAFF-ONLY-EXPLANATION-MARKER"
    await db.transactions.insert_one(
        {
            "_id": tx_id,
            "from_account_id": SOURCE_ACCOUNT_ID,
            "to_account_id": DEST_ACCOUNT_ID,
            "from_iban": SOURCE_ACCOUNT["iban"],
            "to_iban": DEST_ACCOUNT["iban"],
            "amount_minor": 99_000,
            "currency": "RON",
            "description": "",
            "category": "shopping",
            "type": "transfer",
            "status": "pending_review",
            "recognized": False,
            "reported": False,
            "created_at": datetime.now(timezone.utc),
            "hold": {"expires_at": datetime.now(timezone.utc) + timedelta(hours=24), "resolution": None},
            "risk": {"tier": "held", "phrase": "Tranzacția a fost reținută pentru verificare.", "status": "ready"},
        }
    )
    await db.fraud_evaluations.insert_one(
        {
            "transaction_id": tx_id,
            "user_id": USER_ID,
            "status": "ok",
            "score": 95,
            "fired_rules": [],
            "decision_would_apply": "hold",
            "ruleset_version": "test-1",
            "shadow_mode": False,
            "evaluated_at": datetime.now(timezone.utc),
            "error": None,
            "created_at": datetime.now(timezone.utc),
            "guardian": {
                "status": "ready",
                "staff_explanation": marker,
                "customer_tier": "held",
                "customer_phrase": "Tranzacția a fost reținută pentru verificare.",
                "source": "llm",
                "generated_at": datetime.now(timezone.utc),
                "model": "gpt-5-mini",
            },
        }
    )

    detail_response = await client.get(f"/transactions/{tx_id}", headers=AUTH_HEADER)
    assert detail_response.status_code == 200
    assert marker not in detail_response.text

    list_response = await client.get("/transactions", headers=AUTH_HEADER)
    assert list_response.status_code == 200
    assert marker not in list_response.text


async def test_dev03_fails_open_when_auth_service_unreachable(monkeypatch):
    """DEV-03 e singurul network hop al motorului — dacă auth-service nu
    răspunde, regula pur și simplu nu se declanșează, niciodată confundată
    cu 'nicio înrolare recentă' (vezi context.py)."""
    monkeypatch.setattr("app.config.settings.auth_service_url", "http://127.0.0.1:1")  # port închis, eșec rapid

    facts = await context._build_device_facts(user_id="whoever")
    assert facts.data_available is False
    assert facts.latest_passkey_created_at is None
