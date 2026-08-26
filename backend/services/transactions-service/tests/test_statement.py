"""Teste pentru extrasul de cont (PDF).

Trei categorii:
  - reconstrucția soldurilor (funcție PURĂ, fără DB) — testată direct, cu
    mișcări sintetice (shape generic — vezi app/statement.py), verificând
    valorile numerice exact.
  - merge-ul transferuri + schimb valutar (generate_account_statement) —
    verifică EXACT motivul pentru care reconstruct_statement_balances a
    devenit generică: un cont EUR (sau chiar contul curent, pe latura RON)
    trebuie să reflecte și mișcările din exchange-service, nu doar tx_db.
  - endpoint-ul HTTP (mockuri accounts-service/auth-service/exchange-service
    ca în test_transfers.py) — verificăm doar "e un PDF valid, cu statusul/
    header-ele corecte", nu conținutul (ar necesita o librărie de parsare
    PDF doar pentru teste).
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from app import service as service_module
from app.config import settings
from app.database import get_database
from app.main import app
from app.statement import reconstruct_statement_balances

USER_ID = str(ObjectId())
SOURCE_ACCOUNT_ID = str(ObjectId())
DEST_ACCOUNT_ID = str(ObjectId())
EUR_ACCOUNT_ID = str(ObjectId())

SOURCE_ACCOUNT = {
    "id": SOURCE_ACCOUNT_ID,
    "user_id": USER_ID,
    "iban": "RO11MAES0000000000000001",
    "currency": "RON",
    "balance_minor": 100_000,
    "status": "active",
    "account_type": "current",
}

DEST_ACCOUNT = {
    "id": DEST_ACCOUNT_ID,
    "user_id": str(ObjectId()),
    "iban": "RO22MAES0000000000000002",
    "currency": "RON",
    "balance_minor": 0,
    "status": "active",
}

EUR_ACCOUNT = {
    "id": EUR_ACCOUNT_ID,
    "user_id": USER_ID,
    "iban": "RO33MAES0000000000000003",
    "currency": "EUR",
    "balance_minor": 20_000,  # 200,00 EUR
    "status": "active",
    "account_type": "eur",
}


def _make_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "email": "test@example.com", "iat": now, "exp": now + timedelta(minutes=30)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


AUTH_HEADER = {"Authorization": f"Bearer {_make_token(USER_ID)}"}


# --- Reconstrucția soldurilor (funcție pură) --------------------------------


def _movement(delta_minor: int, days_ago: int, description: str = "test", category: str = "other") -> dict:
    return {
        "created_at": datetime(2026, 1, 20) - timedelta(days=days_ago),
        "delta_minor": delta_minor,
        "description": description,
        "category": category,
    }


def test_reconstruct_balances_no_movements():
    opening, closing, lines = reconstruct_statement_balances(
        current_balance_minor=50_000,
        movements=[],
        date_from=datetime(2026, 1, 1),
        date_to=datetime(2026, 1, 31),
    )
    assert opening == 50_000
    assert closing == 50_000
    assert lines == []


def test_reconstruct_balances_period_and_after():
    # Sold curent 100.000. O încasare de 30.000 ACUM 10 zile (în perioadă) și
    # o plată de 10.000 ACUM 1 zi (DUPĂ perioadă, 20-31 ian < azi-1zi).
    movements = [
        _movement(+30_000, days_ago=10),  # în perioadă
        _movement(-10_000, days_ago=1),  # după perioadă
    ]
    opening, closing, lines = reconstruct_statement_balances(
        current_balance_minor=100_000,
        movements=movements,
        date_from=datetime(2026, 1, 1),
        date_to=datetime(2026, 1, 15),
    )
    # net_after = -10.000 (plata de după perioadă) => closing = 100.000 - (-10.000) = 110.000
    assert closing == 110_000
    # net_in_period = +30.000 => opening = 110.000 - 30.000 = 80.000
    assert opening == 80_000
    assert len(lines) == 1
    assert lines[0]["running_balance_minor"] == 110_000  # 80.000 + 30.000


def test_reconstruct_balances_running_balance_multiple_lines():
    movements = [
        _movement(-20_000, days_ago=12),
        _movement(+50_000, days_ago=8),
        _movement(-5_000, days_ago=3),
    ]
    opening, closing, lines = reconstruct_statement_balances(
        current_balance_minor=125_000,
        movements=movements,
        date_from=datetime(2026, 1, 1),
        date_to=datetime(2026, 1, 31),
    )
    assert closing == 125_000  # nimic după perioadă
    # net_in_period = -20.000 + 50.000 - 5.000 = +25.000 => opening = 100.000
    assert opening == 100_000
    running_values = [line["running_balance_minor"] for line in lines]
    assert running_values == [80_000, 130_000, 125_000]


def test_reconstruct_balances_sorts_unordered_input():
    """Apelantul (generate_account_statement) concatenează transferuri +
    schimburi valutare fără să le sorteze — funcția pură trebuie să
    sorteze ea însăși, ca soldul curent (running) să iasă corect."""
    movements = [
        _movement(-5_000, days_ago=3),
        _movement(-20_000, days_ago=12),
        _movement(+50_000, days_ago=8),
    ]
    _, _, lines = reconstruct_statement_balances(
        current_balance_minor=125_000,
        movements=movements,
        date_from=datetime(2026, 1, 1),
        date_to=datetime(2026, 1, 31),
    )
    assert [line["running_balance_minor"] for line in lines] == [80_000, 130_000, 125_000]


# --- Endpoint HTTP -----------------------------------------------------------


@pytest.fixture(autouse=True)
async def clean_transactions():
    await get_database().transactions.delete_many({})
    yield
    await get_database().transactions.delete_many({})


@pytest.fixture
def mock_accounts(monkeypatch):
    state = {"source": dict(SOURCE_ACCOUNT), "destination": dict(DEST_ACCOUNT), "eur": dict(EUR_ACCOUNT)}
    exchanges: list[dict] = []

    async def fake_get_by_user(user_id: str) -> dict:
        return state["source"]

    async def fake_get_by_id(account_id: str, user_id: str) -> dict:
        if account_id == EUR_ACCOUNT_ID:
            return state["eur"]
        return state["source"]

    async def fake_get_user_name(user_id: str):
        return "Octavia Stefan" if user_id == USER_ID else "Andrei Popescu"

    async def fake_get_exchanges_for_user(user_id: str) -> list[dict]:
        return exchanges

    monkeypatch.setattr("app.service._get_account_by_user", fake_get_by_user)
    monkeypatch.setattr("app.service._get_account_by_id", fake_get_by_id)
    monkeypatch.setattr("app.service._get_user_name", fake_get_user_name)
    monkeypatch.setattr("app.service._get_exchanges_for_user", fake_get_exchanges_for_user)
    return {"state": state, "exchanges": exchanges}


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_statement_returns_valid_pdf(client: AsyncClient, mock_accounts):
    now = datetime.now(timezone.utc)
    await get_database().transactions.insert_one(
        {
            "from_account_id": SOURCE_ACCOUNT_ID,
            "to_account_id": DEST_ACCOUNT_ID,
            "from_iban": SOURCE_ACCOUNT["iban"],
            "to_iban": DEST_ACCOUNT["iban"],
            "from_name": "Octavia Stefan",
            "to_name": "Andrei Popescu",
            "amount_minor": 15_000,
            "currency": "RON",
            "description": "Chirie",
            "category": "housing",
            "type": "transfer",
            "status": "completed",
            "recognized": False,
            "reported": False,
            "created_at": now - timedelta(days=2),
        }
    )

    response = await client.get(
        "/transactions/statement",
        params={
            "date_from": (now - timedelta(days=30)).isoformat(),
            "date_to": now.isoformat(),
        },
        headers=AUTH_HEADER,
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment" in response.headers["content-disposition"]
    assert response.content[:4] == b"%PDF"


async def test_statement_empty_period_still_valid_pdf(client: AsyncClient, mock_accounts):
    now = datetime.now(timezone.utc)
    response = await client.get(
        "/transactions/statement",
        params={
            "date_from": (now - timedelta(days=5)).isoformat(),
            "date_to": now.isoformat(),
        },
        headers=AUTH_HEADER,
    )
    assert response.status_code == 200
    assert response.content[:4] == b"%PDF"


async def test_statement_rejects_inverted_range(client: AsyncClient, mock_accounts):
    now = datetime.now(timezone.utc)
    response = await client.get(
        "/transactions/statement",
        params={
            "date_from": now.isoformat(),
            "date_to": (now - timedelta(days=10)).isoformat(),
        },
        headers=AUTH_HEADER,
    )
    assert response.status_code == 400


async def test_statement_requires_auth(client: AsyncClient):
    now = datetime.now(timezone.utc)
    response = await client.get(
        "/transactions/statement",
        params={"date_from": (now - timedelta(days=5)).isoformat(), "date_to": now.isoformat()},
    )
    assert response.status_code == 401


async def test_statement_for_other_account_uses_account_id(client: AsyncClient, mock_accounts):
    """account_id explicit -> _get_account_by_id, NU _get_account_by_user
    (contul EUR, nu contul curent)."""
    now = datetime.now(timezone.utc)
    response = await client.get(
        "/transactions/statement",
        params={
            "date_from": (now - timedelta(days=5)).isoformat(),
            "date_to": now.isoformat(),
            "account_id": EUR_ACCOUNT_ID,
        },
        headers=AUTH_HEADER,
    )
    assert response.status_code == 200
    assert response.content[:4] == b"%PDF"


async def test_generate_statement_merges_exchange_movements_for_eur_account(mock_accounts):
    """Un cont EUR se alimentează prin schimb valutar (nu transfer IBAN) —
    fără merge-ul din generate_account_statement, soldul de început ar
    ieși greșit. Testăm direct funcția de business (nu doar "e un PDF
    valid"), ca regresia asta să fie prinsă dacă cineva rupe merge-ul."""
    now = datetime.now(timezone.utc)
    mock_accounts["exchanges"].append(
        {
            "id": str(ObjectId()),
            "from_currency": "RON",
            "to_currency": "EUR",
            "amount_minor": 50_000,
            "received_minor": 10_000,  # +100,00 EUR creditate în contul EUR
            "applied_rate": 5.0,
            "commission_minor": 0,
            "created_at": (now - timedelta(days=2)).isoformat(),
        }
    )

    pdf_bytes, filename = await service_module.generate_account_statement(
        USER_ID, now - timedelta(days=10), now, account_id=EUR_ACCOUNT_ID
    )
    assert pdf_bytes[:4] == b"%PDF"
    assert EUR_ACCOUNT["iban"] in filename


async def test_generate_statement_current_account_includes_ron_leg_of_exchange(mock_accounts):
    """Contul curent (RON) e afectat de latura RON a unui schimb valutar,
    la fel ca EUR mai sus — nu doar conturile în valută."""
    now = datetime.now(timezone.utc)
    mock_accounts["exchanges"].append(
        {
            "id": str(ObjectId()),
            "from_currency": "RON",
            "to_currency": "EUR",
            "amount_minor": 50_000,  # -500,00 RON debitate din contul curent
            "received_minor": 10_000,
            "applied_rate": 5.0,
            "commission_minor": 0,
            "created_at": (now - timedelta(days=2)).isoformat(),
        }
    )

    pdf_bytes, filename = await service_module.generate_account_statement(
        USER_ID, now - timedelta(days=10), now, account_id=None
    )
    assert pdf_bytes[:4] == b"%PDF"
    assert SOURCE_ACCOUNT["iban"] in filename


async def test_generate_statement_exchange_service_unreachable_degrades_gracefully(monkeypatch, mock_accounts):
    """Dacă exchange-service e jos, extrasul tot se generează — doar fără
    liniile de schimb valutar (degradare grațioasă, ca restul apelurilor
    cross-service din acest fișier)."""
    monkeypatch.setattr("app.service._get_exchanges_for_user", service_module._get_exchanges_for_user)
    monkeypatch.setattr("app.config.settings.exchange_service_url", "http://exchange-service-nu-exista:9999")

    now = datetime.now(timezone.utc)
    pdf_bytes, _ = await service_module.generate_account_statement(
        USER_ID, now - timedelta(days=10), now, account_id=EUR_ACCOUNT_ID
    )
    assert pdf_bytes[:4] == b"%PDF"
