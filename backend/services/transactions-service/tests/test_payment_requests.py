"""
Teste pentru cereri de plată (link/QR, tip "Request Money") —
app/service.py (create/get/list/pay/cancel_payment_request) și
app/routers/payment_requests.py.

Apelurile către accounts-service/auth-service sunt mock-uite, la fel ca în
test_transfers.py — dar aici cu DOI useri distincți (cel care cere bani și
cel care plătește), fiecare cu propriul cont/IBAN, ca să testăm real
fluxul "altcineva plătește cererea mea".

Rulare: vezi antetul test_transfers.py.
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

REQUESTER_ID = str(ObjectId())
PAYER_ID = str(ObjectId())
REQUESTER_ACCOUNT_ID = str(ObjectId())
PAYER_ACCOUNT_ID = str(ObjectId())

REQUESTER_ACCOUNT = {
    "id": REQUESTER_ACCOUNT_ID,
    "user_id": REQUESTER_ID,
    "iban": "RO11MAES0000000000000001",
    "currency": "RON",
    "balance_minor": 0,
    "status": "active",
}

PAYER_ACCOUNT = {
    "id": PAYER_ACCOUNT_ID,
    "user_id": PAYER_ID,
    "iban": "RO22MAES0000000000000002",
    "currency": "RON",
    "balance_minor": 100_000,
    "status": "active",
}


def _make_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "email": "test@example.com", "iat": now, "exp": now + timedelta(minutes=30)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


REQUESTER_HEADER = {"Authorization": f"Bearer {_make_token(REQUESTER_ID)}"}
PAYER_HEADER = {"Authorization": f"Bearer {_make_token(PAYER_ID)}"}


@pytest.fixture(autouse=True)
async def clean_payment_requests():
    db = get_database()
    await db.transactions.delete_many({})
    await db.payment_requests.delete_many({})
    yield
    await db.transactions.delete_many({})
    await db.payment_requests.delete_many({})


@pytest.fixture
def mock_accounts(monkeypatch):
    """Doi useri distincți, fiecare cu contul lui — spre deosebire de
    `mock_accounts` din test_transfers.py (un singur cont mereu întors),
    aici avem nevoie ca `_get_account_by_user` să rezolve DIFERIT în
    funcție de cine e autentificat, ca să simulăm real "A cere, B plătește"."""
    state = {"requester": dict(REQUESTER_ACCOUNT), "payer": dict(PAYER_ACCOUNT)}
    by_user_id = {REQUESTER_ID: "requester", PAYER_ID: "payer"}

    async def fake_get_by_user(user_id: str) -> dict:
        key = by_user_id.get(user_id)
        if key is None:
            raise AssertionError(f"unexpected user_id in test: {user_id}")
        return state[key]

    async def fake_get_by_iban(iban: str):
        for account in state.values():
            if account["iban"] == iban:
                return account
        return None

    async def fake_apply_transfer(from_id: str, to_id: str, amount_minor: int) -> dict:
        for account in state.values():
            if account["id"] == from_id:
                account["balance_minor"] -= amount_minor
            if account["id"] == to_id:
                account["balance_minor"] += amount_minor
        return {"ok": True}

    async def fake_get_user_name(user_id: str) -> str | None:
        names = {REQUESTER_ID: "Octavia Stefan", PAYER_ID: "Andrei Popescu"}
        return names.get(user_id)

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


async def _create_request(client: AsyncClient, description: str = "Cina de aseară", amount_minor: int = 2_500) -> dict:
    response = await client.post(
        "/transactions/payment-requests",
        json={"amount_minor": amount_minor, "description": description},
        headers=REQUESTER_HEADER,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_payment_request_succeeds(client: AsyncClient, mock_accounts):
    body = await _create_request(client)
    assert body["status"] == "open"
    assert body["amount_minor"] == 2_500
    assert body["currency"] == "RON"
    assert body["requester_iban"] == REQUESTER_ACCOUNT["iban"]
    assert body["requester_name"] == "Octavia Stefan"
    assert body["paid_at"] is None
    assert body["paid_by_name"] is None


async def test_create_payment_request_blocks_dangerous_description(client: AsyncClient, mock_accounts):
    """Diferit de un transfer normal (unde termenii marcați doar dau un
    avertisment — vezi test_content_screening.py) — o cerere de plată e un
    link/QR menit să fie trimis mai departe, deci aici BLOCĂM crearea în
    loc doar să avertizăm (vezi comentariul din models.py::PaymentRequestOut)."""
    response = await client.post(
        "/transactions/payment-requests",
        json={"amount_minor": 100, "description": "bomba"},
        headers=REQUESTER_HEADER,
    )
    assert response.status_code == 400
    assert "activități ilegale" in response.json()["detail"]

    # nu s-a creat nimic
    mine = await client.get("/transactions/payment-requests/mine", headers=REQUESTER_HEADER)
    assert mine.json() == []


async def test_create_payment_request_rejects_non_positive_amount(client: AsyncClient, mock_accounts):
    response = await client.post(
        "/transactions/payment-requests",
        json={"amount_minor": 0, "description": "x"},
        headers=REQUESTER_HEADER,
    )
    assert response.status_code == 422


async def test_create_payment_request_requires_auth(client: AsyncClient, mock_accounts):
    response = await client.post(
        "/transactions/payment-requests", json={"amount_minor": 100, "description": "x"}
    )
    assert response.status_code == 401


async def test_any_authenticated_user_can_view_someone_elses_request(client: AsyncClient, mock_accounts):
    """Cine primește link-ul (payer) trebuie să poată vedea suma/descrierea
    ÎNAINTE de a plăti — nu doar cel care a creat cererea."""
    created = await _create_request(client)
    response = await client.get(f"/transactions/payment-requests/{created['id']}", headers=PAYER_HEADER)
    assert response.status_code == 200
    assert response.json()["amount_minor"] == 2_500


async def test_get_payment_request_requires_auth(client: AsyncClient, mock_accounts):
    created = await _create_request(client)
    response = await client.get(f"/transactions/payment-requests/{created['id']}")
    assert response.status_code == 401


async def test_get_nonexistent_payment_request_404(client: AsyncClient, mock_accounts):
    response = await client.get(f"/transactions/payment-requests/{ObjectId()}", headers=PAYER_HEADER)
    assert response.status_code == 404


async def test_get_payment_request_invalid_id_404(client: AsyncClient, mock_accounts):
    response = await client.get("/transactions/payment-requests/not-an-object-id", headers=PAYER_HEADER)
    assert response.status_code == 404


async def test_list_my_payment_requests_only_shows_own(client: AsyncClient, mock_accounts):
    await _create_request(client)
    await _create_request(client, description="Al doilea")

    mine = await client.get("/transactions/payment-requests/mine", headers=REQUESTER_HEADER)
    assert mine.status_code == 200
    assert len(mine.json()) == 2

    payer_mine = await client.get("/transactions/payment-requests/mine", headers=PAYER_HEADER)
    assert payer_mine.status_code == 200
    assert payer_mine.json() == []


async def test_pay_payment_request_moves_money_and_marks_paid(client: AsyncClient, mock_accounts):
    created = await _create_request(client)

    response = await client.post(f"/transactions/payment-requests/{created['id']}/pay", headers=PAYER_HEADER)
    assert response.status_code == 200, response.text
    transaction = response.json()
    assert transaction["status"] == "completed"
    assert transaction["direction"] == "outgoing"
    assert transaction["amount_minor"] == 2_500
    assert transaction["counterparty_iban"] == REQUESTER_ACCOUNT["iban"]

    # banii chiar s-au mutat (via mock_accounts, care ține stare reală)
    assert mock_accounts["payer"]["balance_minor"] == 100_000 - 2_500
    assert mock_accounts["requester"]["balance_minor"] == 2_500

    # cererea reflectă plata
    requester_view = await client.get(f"/transactions/payment-requests/{created['id']}", headers=REQUESTER_HEADER)
    body = requester_view.json()
    assert body["status"] == "paid"
    assert body["paid_by_name"] == "Andrei Popescu"
    assert body["paid_at"] is not None


async def test_cannot_pay_own_payment_request(client: AsyncClient, mock_accounts):
    created = await _create_request(client)
    response = await client.post(f"/transactions/payment-requests/{created['id']}/pay", headers=REQUESTER_HEADER)
    assert response.status_code == 400


async def test_cannot_pay_payment_request_twice(client: AsyncClient, mock_accounts):
    created = await _create_request(client)
    first = await client.post(f"/transactions/payment-requests/{created['id']}/pay", headers=PAYER_HEADER)
    assert first.status_code == 200

    second = await client.post(f"/transactions/payment-requests/{created['id']}/pay", headers=PAYER_HEADER)
    assert second.status_code == 409


async def test_pay_nonexistent_payment_request_404(client: AsyncClient, mock_accounts):
    response = await client.post(f"/transactions/payment-requests/{ObjectId()}/pay", headers=PAYER_HEADER)
    assert response.status_code == 404


async def test_pay_payment_request_requires_auth(client: AsyncClient, mock_accounts):
    created = await _create_request(client)
    response = await client.post(f"/transactions/payment-requests/{created['id']}/pay")
    assert response.status_code == 401


async def test_owner_can_cancel_open_payment_request(client: AsyncClient, mock_accounts):
    created = await _create_request(client)
    response = await client.post(f"/transactions/payment-requests/{created['id']}/cancel", headers=REQUESTER_HEADER)
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    # o cerere anulată nu mai poate fi plătită
    pay = await client.post(f"/transactions/payment-requests/{created['id']}/pay", headers=PAYER_HEADER)
    assert pay.status_code == 409
    assert mock_accounts["payer"]["balance_minor"] == 100_000  # banii nu s-au mișcat


async def test_non_owner_cannot_cancel_payment_request(client: AsyncClient, mock_accounts):
    """404, nu 403 — nu confirmăm existența unei cereri a altcuiva (vezi
    convenția de peste tot din acest serviciu, ex. cancel_own_hold)."""
    created = await _create_request(client)
    response = await client.post(f"/transactions/payment-requests/{created['id']}/cancel", headers=PAYER_HEADER)
    assert response.status_code == 404


async def test_cannot_cancel_already_paid_request(client: AsyncClient, mock_accounts):
    created = await _create_request(client)
    paid = await client.post(f"/transactions/payment-requests/{created['id']}/pay", headers=PAYER_HEADER)
    assert paid.status_code == 200

    cancel = await client.post(f"/transactions/payment-requests/{created['id']}/cancel", headers=REQUESTER_HEADER)
    assert cancel.status_code == 409


async def test_expired_payment_request_cannot_be_paid(client: AsyncClient, mock_accounts):
    created = await _create_request(client)
    db = get_database()
    # simulăm trecerea timpului direct în DB — vezi _payment_request_
    # effective_status (expirare LENEȘĂ, calculată la citire, nu printr-un
    # loop de fundal).
    await db.payment_requests.update_one(
        {"_id": ObjectId(created["id"])},
        {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(days=1)}},
    )

    view = await client.get(f"/transactions/payment-requests/{created['id']}", headers=PAYER_HEADER)
    assert view.json()["status"] == "expired"

    pay = await client.post(f"/transactions/payment-requests/{created['id']}/pay", headers=PAYER_HEADER)
    assert pay.status_code == 409
    assert mock_accounts["payer"]["balance_minor"] == 100_000
