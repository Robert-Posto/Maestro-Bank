"""
Teste pentru documentele de semnat (eSign) — support-service.

Mock-uiește apelurile HTTP către auth-service (căutare clienți, rezolvare
nume, verificare parolă/passkey) — la fel ca test_transfers_hold_integration.py
din transactions-service (mock pe granița serviciu-la-serviciu, nu pe Mongo).

Rulare:
    docker compose exec support-service pip install -r requirements-dev.txt -q
    docker compose exec -e MONGO_URL=mongodb://mongodb:27017/support_db_test support-service python -m pytest -q
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
OTHER_USER_ID = str(ObjectId())
STAFF_USER_ID = str(ObjectId())

VALID_PDF_DATA_URI = "data:application/pdf;base64," + "QQ==" * 50  # conținut fals — doar prefixul e validat
CORRECT_PASSWORD = "ParolaCorecta123"


def _make_token(user_id: str, role: str = "customer") -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "email": "test@example.com", "role": role, "iat": now, "exp": now + timedelta(minutes=5)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


AUTH_HEADER = {"Authorization": f"Bearer {_make_token(USER_ID)}"}
OTHER_AUTH_HEADER = {"Authorization": f"Bearer {_make_token(OTHER_USER_ID)}"}
STAFF_HEADER = {"Authorization": f"Bearer {_make_token(STAFF_USER_ID, role='staff')}"}


@pytest.fixture(autouse=True)
async def clean_documents():
    db = get_database()
    await db.documents.delete_many({})
    await db.notifications.delete_many({})
    yield
    await db.documents.delete_many({})
    await db.notifications.delete_many({})


@pytest.fixture
def mock_auth_service(monkeypatch):
    """Mock-uiește TOATE apelurile HTTP către auth-service — căutare
    clienți, rezolvare nume, verificare parolă/passkey."""
    state = {"password_valid": True, "webauthn_valid": True}

    async def fake_resolve_customer_name(user_id: str) -> str:
        return "Test User"

    async def fake_search_customers(query: str) -> list[dict]:
        if not query.strip():
            return []
        return [{"id": USER_ID, "first_name": "Test", "last_name": "User", "email": "test@example.com"}]

    async def fake_verify_password(user_id: str, password: str) -> bool:
        return state["password_valid"] and password == CORRECT_PASSWORD

    async def fake_verify_webauthn(user_id: str, document_id: str, challenge_id: str, assertion: dict) -> bool:
        return state["webauthn_valid"]

    monkeypatch.setattr("app.service._resolve_customer_name", fake_resolve_customer_name)
    monkeypatch.setattr("app.service.search_customers", fake_search_customers)
    monkeypatch.setattr("app.service._verify_password_with_auth_service", fake_verify_password)
    monkeypatch.setattr("app.service._verify_webauthn_with_auth_service", fake_verify_webauthn)
    return state


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _send_document(client: AsyncClient, user_id: str = USER_ID, title: str = "Contract de credit") -> dict:
    response = await client.post(
        "/staff/documents",
        json={"user_id": user_id, "title": title, "pdf_data": VALID_PDF_DATA_URI},
        headers=STAFF_HEADER,
    )
    assert response.status_code == 201
    return response.json()


# --- Trimitere (personal) --------------------------------------------------


async def test_staff_can_send_document(client: AsyncClient, mock_auth_service):
    body = await _send_document(client)
    assert body["title"] == "Contract de credit"
    assert body["status"] == "pending"
    assert body["customer_name"] == "Test User"
    assert body["user_id"] == USER_ID


async def test_sending_document_creates_notification_for_customer(client: AsyncClient, mock_auth_service):
    await _send_document(client)

    notifications = await get_database().notifications.find({"user_id": USER_ID}).to_list(length=10)
    assert len(notifications) == 1
    assert notifications[0]["kind"] == "document_sign"
    assert "Contract de credit" in notifications[0]["text"]


async def test_non_staff_cannot_send_document(client: AsyncClient, mock_auth_service):
    response = await client.post(
        "/staff/documents",
        json={"user_id": USER_ID, "title": "x", "pdf_data": VALID_PDF_DATA_URI},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 403


async def test_send_document_rejects_non_pdf_data_uri(client: AsyncClient, mock_auth_service):
    response = await client.post(
        "/staff/documents",
        json={"user_id": USER_ID, "title": "x", "pdf_data": "data:image/png;base64,QQ=="},
        headers=STAFF_HEADER,
    )
    assert response.status_code == 422


# --- Listare/vizualizare (client) ------------------------------------------


async def test_customer_lists_only_own_documents(client: AsyncClient, mock_auth_service):
    await _send_document(client, user_id=USER_ID)

    mine = await client.get("/documents", headers=AUTH_HEADER)
    assert mine.status_code == 200
    assert len(mine.json()) == 1

    others = await client.get("/documents", headers=OTHER_AUTH_HEADER)
    assert others.status_code == 200
    assert others.json() == []


async def test_document_list_excludes_pdf_data(client: AsyncClient, mock_auth_service):
    await _send_document(client)

    response = await client.get("/documents", headers=AUTH_HEADER)
    assert "pdf_data" not in response.json()[0]


async def test_customer_can_view_own_document_with_pdf_data(client: AsyncClient, mock_auth_service):
    sent = await _send_document(client)

    response = await client.get(f"/documents/{sent['id']}", headers=AUTH_HEADER)
    assert response.status_code == 200
    assert response.json()["pdf_data"] == VALID_PDF_DATA_URI


async def test_customer_cannot_view_another_users_document(client: AsyncClient, mock_auth_service):
    sent = await _send_document(client, user_id=USER_ID)

    response = await client.get(f"/documents/{sent['id']}", headers=OTHER_AUTH_HEADER)
    assert response.status_code == 404


# --- Semnare -----------------------------------------------------------


async def test_sign_with_correct_password_succeeds(client: AsyncClient, mock_auth_service):
    sent = await _send_document(client)

    response = await client.post(f"/documents/{sent['id']}/sign", json={"password": CORRECT_PASSWORD}, headers=AUTH_HEADER)
    assert response.status_code == 200
    assert response.json()["status"] == "signed"

    stored = await get_database().documents.find_one({"_id": ObjectId(sent["id"])})
    assert stored["sign_method"] == "password"
    assert stored["signed_at"] is not None


async def test_sign_with_wrong_password_rejected_and_stays_pending(client: AsyncClient, mock_auth_service):
    sent = await _send_document(client)

    response = await client.post(f"/documents/{sent['id']}/sign", json={"password": "gresita"}, headers=AUTH_HEADER)
    assert response.status_code == 401

    stored = await get_database().documents.find_one({"_id": ObjectId(sent["id"])})
    assert stored["status"] == "pending"


async def test_sign_with_webauthn_succeeds(client: AsyncClient, mock_auth_service):
    sent = await _send_document(client)

    response = await client.post(
        f"/documents/{sent['id']}/sign",
        json={"webauthn_challenge_id": "chal-1", "webauthn_assertion": {"id": "cred-1"}},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 200
    stored = await get_database().documents.find_one({"_id": ObjectId(sent["id"])})
    assert stored["sign_method"] == "webauthn"


async def test_sign_requires_exactly_one_method(client: AsyncClient, mock_auth_service):
    sent = await _send_document(client)

    neither = await client.post(f"/documents/{sent['id']}/sign", json={}, headers=AUTH_HEADER)
    assert neither.status_code == 422

    both = await client.post(
        f"/documents/{sent['id']}/sign",
        json={"password": CORRECT_PASSWORD, "webauthn_challenge_id": "c", "webauthn_assertion": {"id": "x"}},
        headers=AUTH_HEADER,
    )
    assert both.status_code == 422


async def test_signing_twice_conflicts(client: AsyncClient, mock_auth_service):
    sent = await _send_document(client)
    await client.post(f"/documents/{sent['id']}/sign", json={"password": CORRECT_PASSWORD}, headers=AUTH_HEADER)

    response = await client.post(f"/documents/{sent['id']}/sign", json={"password": CORRECT_PASSWORD}, headers=AUTH_HEADER)
    assert response.status_code == 409


async def test_cannot_sign_someone_elses_document(client: AsyncClient, mock_auth_service):
    sent = await _send_document(client, user_id=USER_ID)

    response = await client.post(
        f"/documents/{sent['id']}/sign", json={"password": CORRECT_PASSWORD}, headers=OTHER_AUTH_HEADER
    )
    assert response.status_code == 404


# --- Anulare (personal) --------------------------------------------------


async def test_staff_can_cancel_pending_document(client: AsyncClient, mock_auth_service):
    sent = await _send_document(client)

    response = await client.delete(f"/staff/documents/{sent['id']}", headers=STAFF_HEADER)
    assert response.status_code == 204

    stored = await get_database().documents.find_one({"_id": ObjectId(sent["id"])})
    assert stored["status"] == "cancelled"


async def test_cannot_sign_cancelled_document(client: AsyncClient, mock_auth_service):
    sent = await _send_document(client)
    await client.delete(f"/staff/documents/{sent['id']}", headers=STAFF_HEADER)

    response = await client.post(f"/documents/{sent['id']}/sign", json={"password": CORRECT_PASSWORD}, headers=AUTH_HEADER)
    assert response.status_code == 409


async def test_cannot_cancel_already_signed_document(client: AsyncClient, mock_auth_service):
    sent = await _send_document(client)
    await client.post(f"/documents/{sent['id']}/sign", json={"password": CORRECT_PASSWORD}, headers=AUTH_HEADER)

    response = await client.delete(f"/staff/documents/{sent['id']}", headers=STAFF_HEADER)
    assert response.status_code == 409


async def test_non_staff_cannot_cancel_document(client: AsyncClient, mock_auth_service):
    sent = await _send_document(client)

    response = await client.delete(f"/staff/documents/{sent['id']}", headers=AUTH_HEADER)
    assert response.status_code == 403


# --- Listare de personal + căutare clienți ---------------------------------


async def test_staff_lists_all_sent_documents(client: AsyncClient, mock_auth_service):
    await _send_document(client, title="Primul")
    await _send_document(client, title="Al doilea")

    response = await client.get("/staff/documents", headers=STAFF_HEADER)
    assert response.status_code == 200
    assert len(response.json()) == 2
    assert "pdf_data" not in response.json()[0]


async def test_staff_search_customers(client: AsyncClient, mock_auth_service):
    response = await client.get("/staff/customers/search", params={"q": "test"}, headers=STAFF_HEADER)
    assert response.status_code == 200
    assert response.json()[0]["email"] == "test@example.com"


async def test_non_staff_cannot_search_customers(client: AsyncClient, mock_auth_service):
    response = await client.get("/staff/customers/search", params={"q": "test"}, headers=AUTH_HEADER)
    assert response.status_code == 403
