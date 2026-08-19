"""
Teste pentru transactions-service.

Apelurile către accounts-service (_get_account_by_user, _get_account_by_iban,
_apply_transfer) sunt MOCK-uite aici, intenționat — nu e responsabilitatea
acestor teste să (re)verifice accounts-service (are propriile teste), iar
altfel ar fi nevoie de accounts-service pornit și s-ar polua accounts_db
real la fiecare rulare.

Rulare (cu stack-ul pornit prin `docker compose up`, bază de TEST
separată pentru tx_db):

    docker compose exec transactions-service pip install pytest==8.3.3 pytest-asyncio==0.24.0 -q
    docker compose exec -e MONGO_URL=mongodb://mongodb:27017/tx_db_test transactions-service python -m pytest -q
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import get_database
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
    """Config implicit: cont sursă cu 1.000 RON, destinație validă și diferită."""
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

    monkeypatch.setattr("app.service._get_account_by_user", fake_get_by_user)
    monkeypatch.setattr("app.service._get_account_by_iban", fake_get_by_iban)
    monkeypatch.setattr("app.service._apply_transfer", fake_apply_transfer)
    return state


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_transfer_succeeds(client: AsyncClient, mock_accounts):
    response = await client.post(
        "/transactions/transfers",
        json={"to_iban": DEST_ACCOUNT["iban"], "amount_minor": 50_000, "description": "Dinner"},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert body["direction"] == "outgoing"
    assert body["amount_minor"] == 50_000
    assert body["counterparty_iban"] == DEST_ACCOUNT["iban"]

    # sold sursă a scăzut / sold destinație a crescut (verificat via mock)
    assert mock_accounts["source"]["balance_minor"] == 50_000
    assert mock_accounts["destination"]["balance_minor"] == 50_000


async def test_transaction_is_saved_and_listed(client: AsyncClient, mock_accounts):
    await client.post(
        "/transactions/transfers",
        json={"to_iban": DEST_ACCOUNT["iban"], "amount_minor": 10_000, "description": "Test"},
        headers=AUTH_HEADER,
    )

    response = await client.get("/transactions", headers=AUTH_HEADER)
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["status"] == "completed"


async def test_insufficient_balance_rejected(client: AsyncClient, mock_accounts):
    response = await client.post(
        "/transactions/transfers",
        json={"to_iban": DEST_ACCOUNT["iban"], "amount_minor": 999_999, "description": ""},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 409


async def test_same_account_transfer_rejected(client: AsyncClient, mock_accounts):
    mock_accounts["destination"]["id"] = mock_accounts["source"]["id"]

    response = await client.post(
        "/transactions/transfers",
        json={"to_iban": SOURCE_ACCOUNT["iban"], "amount_minor": 1_000, "description": ""},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 400


async def test_negative_transfer_rejected(client: AsyncClient, mock_accounts):
    response = await client.post(
        "/transactions/transfers",
        json={"to_iban": DEST_ACCOUNT["iban"], "amount_minor": -100, "description": ""},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 422  # validare Pydantic


async def test_invalid_destination_rejected(client: AsyncClient, monkeypatch):
    async def fake_get_by_user(user_id: str) -> dict:
        return dict(SOURCE_ACCOUNT)

    async def fake_get_by_iban(iban: str):
        return None  # IBAN inexistent

    monkeypatch.setattr("app.service._get_account_by_user", fake_get_by_user)
    monkeypatch.setattr("app.service._get_account_by_iban", fake_get_by_iban)

    response = await client.post(
        "/transactions/transfers",
        json={"to_iban": "RO99MAES9999999999999999", "amount_minor": 1_000, "description": ""},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 404


async def test_transfer_without_jwt_rejected(client: AsyncClient, mock_accounts):
    response = await client.post(
        "/transactions/transfers",
        json={"to_iban": DEST_ACCOUNT["iban"], "amount_minor": 1_000, "description": ""},
    )
    assert response.status_code == 401


# --- Filtre, detalii, recognize/report, export, paginare, izolare --------
#
# Pentru aceste teste inserăm direct documente în tx_db (nu mai trecem
# prin fluxul complet de transfer) — mai simplu și suficient, fiindcă
# create_transfer e deja acoperit mai sus. `_get_account_by_user` e
# mock-uit per-user, ca să simulăm corect izolarea între useri.

OTHER_USER_ID = str(ObjectId())
OTHER_ACCOUNT_ID = str(ObjectId())
OTHER_ACCOUNT = {
    "id": OTHER_ACCOUNT_ID,
    "user_id": OTHER_USER_ID,
    "iban": "RO33MAES0000000000000003",
    "currency": "RON",
    "balance_minor": 0,
    "status": "active",
}

OTHER_AUTH_HEADER = {"Authorization": f"Bearer {_make_token(OTHER_USER_ID)}"}


@pytest.fixture
def mock_accounts_by_user(monkeypatch):
    """Rezolvă contul SURSĂ diferit, în funcție de user_id — necesar ca
    să putem testa izolarea reală între doi useri distincți."""

    async def fake_get_by_user(user_id: str) -> dict:
        if user_id == OTHER_USER_ID:
            return dict(OTHER_ACCOUNT)
        return dict(SOURCE_ACCOUNT)

    monkeypatch.setattr("app.service._get_account_by_user", fake_get_by_user)


async def _seed_transaction(**overrides) -> dict:
    base = {
        "from_account_id": SOURCE_ACCOUNT_ID,
        "to_account_id": DEST_ACCOUNT_ID,
        "from_iban": SOURCE_ACCOUNT["iban"],
        "to_iban": DEST_ACCOUNT["iban"],
        "amount_minor": 10_000,
        "currency": "RON",
        "description": "Kaufland",
        "category": "groceries",
        "type": "transfer",
        "status": "completed",
        "recognized": False,
        "reported": False,
        "created_at": datetime.now(timezone.utc),
    }
    base.update(overrides)
    result = await get_database().transactions.insert_one(base)
    base["_id"] = result.inserted_id
    return base


async def test_filter_by_category(client: AsyncClient, mock_accounts_by_user):
    await _seed_transaction(category="groceries", description="Kaufland")
    await _seed_transaction(category="entertainment", description="Spotify")

    response = await client.get("/transactions?category=entertainment", headers=AUTH_HEADER)
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["category"] == "entertainment"


async def test_filter_by_direction(client: AsyncClient, mock_accounts_by_user):
    await _seed_transaction(from_account_id=SOURCE_ACCOUNT_ID, to_account_id=DEST_ACCOUNT_ID)  # outgoing
    await _seed_transaction(from_account_id=DEST_ACCOUNT_ID, to_account_id=SOURCE_ACCOUNT_ID)  # incoming

    response = await client.get("/transactions?direction=incoming", headers=AUTH_HEADER)
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["direction"] == "incoming"


async def test_filter_by_amount_range(client: AsyncClient, mock_accounts_by_user):
    await _seed_transaction(amount_minor=5_000)
    await _seed_transaction(amount_minor=50_000)

    response = await client.get("/transactions?min_amount_minor=10000&max_amount_minor=100000", headers=AUTH_HEADER)
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["amount_minor"] == 50_000


async def test_filter_by_search(client: AsyncClient, mock_accounts_by_user):
    await _seed_transaction(description="Kaufland groceries")
    await _seed_transaction(description="Netflix subscription")

    response = await client.get("/transactions?search=netflix", headers=AUTH_HEADER)
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert "Netflix" in items[0]["description"]


async def test_pagination_limit_and_skip(client: AsyncClient, mock_accounts_by_user):
    for i in range(5):
        await _seed_transaction(description=f"tx-{i}", amount_minor=1_000 + i)

    first_page = await client.get("/transactions?limit=2&skip=0", headers=AUTH_HEADER)
    second_page = await client.get("/transactions?limit=2&skip=2", headers=AUTH_HEADER)
    assert len(first_page.json()) == 2
    assert len(second_page.json()) == 2
    assert first_page.json() != second_page.json()


async def test_get_transaction_details(client: AsyncClient, mock_accounts_by_user):
    tx = await _seed_transaction()

    response = await client.get(f"/transactions/{tx['_id']}", headers=AUTH_HEADER)
    assert response.status_code == 200
    assert response.json()["description"] == "Kaufland"


async def test_get_transaction_details_user_isolation(client: AsyncClient, mock_accounts_by_user):
    tx = await _seed_transaction()  # aparține SOURCE_ACCOUNT (USER_ID)

    response = await client.get(f"/transactions/{tx['_id']}", headers=OTHER_AUTH_HEADER)
    assert response.status_code == 404


async def test_recognize_transaction(client: AsyncClient, mock_accounts_by_user):
    tx = await _seed_transaction()

    response = await client.patch(f"/transactions/{tx['_id']}/recognize", headers=AUTH_HEADER)
    assert response.status_code == 200
    assert response.json()["recognized"] is True


async def test_recognize_transaction_user_isolation(client: AsyncClient, mock_accounts_by_user):
    tx = await _seed_transaction()

    response = await client.patch(f"/transactions/{tx['_id']}/recognize", headers=OTHER_AUTH_HEADER)
    assert response.status_code == 404


async def test_report_transaction(client: AsyncClient, mock_accounts_by_user):
    tx = await _seed_transaction()

    response = await client.post(
        f"/transactions/{tx['_id']}/report", json={"reason": "Nu recunosc această tranzacție"}, headers=AUTH_HEADER
    )
    assert response.status_code == 200
    assert response.json()["reported"] is True


async def test_export_csv_contains_filtered_rows_only(client: AsyncClient, mock_accounts_by_user):
    await _seed_transaction(category="groceries", description="Kaufland")
    await _seed_transaction(category="entertainment", description="Spotify")

    response = await client.get("/transactions/export?category=groceries", headers=AUTH_HEADER)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    body = response.text
    assert "Kaufland" in body
    assert "Spotify" not in body


async def test_list_transactions_user_isolation(client: AsyncClient, mock_accounts_by_user):
    await _seed_transaction()  # aparține SOURCE_ACCOUNT (USER_ID)

    response = await client.get("/transactions", headers=OTHER_AUTH_HEADER)
    assert response.status_code == 200
    assert response.json() == []
