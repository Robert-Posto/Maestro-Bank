"""
Teste pentru accounts-service.

Rulare (cu stack-ul pornit prin `docker compose up`, bază de TEST
separată, ca să nu polueze accounts_db real):

    docker compose exec accounts-service pip install pytest==8.3.3 pytest-asyncio==0.24.0 httpx==0.27.2 -q
    docker compose exec -e MONGO_URL=mongodb://mongodb:27017/accounts_db_test accounts-service python -m pytest -q
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

import app.service as service_module
from app.config import settings
from app.database import get_database
from app.main import app

pytestmark = pytest.mark.asyncio


def _make_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "email": "test@example.com", "iat": now, "exp": now + timedelta(minutes=5)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


@pytest.fixture(autouse=True)
async def clean_collections():
    await get_database().accounts.delete_many({})
    await get_database().cards.delete_many({})
    await get_database().beneficiaries.delete_many({})
    yield
    await get_database().accounts.delete_many({})
    await get_database().cards.delete_many({})
    await get_database().beneficiaries.delete_many({})


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _provision(client: AsyncClient) -> tuple[str, dict]:
    user_id = str(ObjectId())  # simulăm un user_id real de auth-service (ObjectId valid)
    response = await client.post("/internal/accounts/provision", json={"user_id": user_id})
    assert response.status_code == 201
    return user_id, response.json()


async def test_account_created_with_zero_balance(client: AsyncClient):
    user_id, body = await _provision(client)
    assert body["account"]["user_id"] == user_id
    assert body["account"]["balance_minor"] == 0
    assert body["account"]["currency"] == "RON"
    assert body["account"]["status"] == "active"
    assert body["card"]["user_id"] == user_id
    assert body["card"]["type"] == "virtual"
    assert len(body["card"]["last_four"]) == 4


async def test_iban_is_unique(client: AsyncClient):
    _, first = await _provision(client)
    _, second = await _provision(client)
    assert first["account"]["iban"] != second["account"]["iban"]
    assert first["account"]["iban"].startswith("RO")
    assert "MAES" in first["account"]["iban"]


async def test_demo_funding_works(client: AsyncClient):
    user_id, _ = await _provision(client)
    token = _make_token(user_id)

    response = await client.post(
        "/dev/fund",
        json={"amount_minor": 1_000_000},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["balance_minor"] == 1_000_000
    assert response.json()["balance"] == "10000.00"


async def test_negative_funding_rejected(client: AsyncClient):
    user_id, _ = await _provision(client)
    token = _make_token(user_id)

    response = await client.post(
        "/dev/fund",
        json={"amount_minor": -500},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422  # validare Pydantic — amount_minor trebuie > 0


async def test_me_without_jwt_rejected(client: AsyncClient):
    response = await client.get("/me")
    assert response.status_code == 401


async def _provision_with_card(client: AsyncClient) -> tuple[str, str, str]:
    user_id, body = await _provision(client)
    return user_id, _make_token(user_id), body["card"]["_id"]


async def test_card_defaults_are_active_and_unfrozen(client: AsyncClient):
    _, body = await _provision(client)
    card = body["card"]
    assert card["is_frozen"] is False
    assert card["online_payments_enabled"] is True
    assert card["contactless_enabled"] is True
    assert card["atm_withdrawals_enabled"] is True
    assert card["international_payments_enabled"] is True
    assert card["daily_limit_minor"] == 500_000


async def test_freeze_and_unfreeze_card(client: AsyncClient):
    _, token, card_id = await _provision_with_card(client)

    frozen = await client.patch(f"/cards/{card_id}/freeze", headers={"Authorization": f"Bearer {token}"})
    assert frozen.status_code == 200
    assert frozen.json()["is_frozen"] is True

    unfrozen = await client.patch(f"/cards/{card_id}/unfreeze", headers={"Authorization": f"Bearer {token}"})
    assert unfrozen.status_code == 200
    assert unfrozen.json()["is_frozen"] is False


async def test_update_card_settings_partial(client: AsyncClient):
    _, token, card_id = await _provision_with_card(client)

    response = await client.patch(
        f"/cards/{card_id}/settings",
        json={"contactless_enabled": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["contactless_enabled"] is False
    # celelalte câmpuri rămân neschimbate (nu au fost trimise)
    assert body["online_payments_enabled"] is True
    assert body["atm_withdrawals_enabled"] is True


async def test_update_card_limit(client: AsyncClient):
    _, token, card_id = await _provision_with_card(client)

    response = await client.patch(
        f"/cards/{card_id}/limits",
        json={"daily_limit_minor": 250_000},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["daily_limit_minor"] == 250_000


async def test_card_controls_require_jwt(client: AsyncClient):
    _, _, card_id = await _provision_with_card(client)
    response = await client.patch(f"/cards/{card_id}/freeze")
    assert response.status_code == 401


async def test_user_cannot_freeze_another_users_card(client: AsyncClient):
    _, _, card_id = await _provision_with_card(client)
    other_user_id, _ = await _provision(client)
    other_token = _make_token(other_user_id)

    response = await client.patch(f"/cards/{card_id}/freeze", headers={"Authorization": f"Bearer {other_token}"})
    assert response.status_code == 404


async def test_create_virtual_card_with_design(client: AsyncClient):
    _, token, _ = await _provision_with_card(client)

    response = await client.post(
        "/cards",
        json={"design": "aurora", "type": "virtual", "is_one_time": False, "pin": "1234"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["design"] == "aurora"
    assert body["type"] == "virtual"
    assert body["is_one_time"] is False
    assert len(body["last_four"]) == 4


async def test_create_card_invalid_design_rejected(client: AsyncClient):
    _, token, _ = await _provision_with_card(client)

    response = await client.post(
        "/cards",
        json={"design": "does-not-exist", "type": "virtual"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


async def test_one_time_card_must_be_virtual(client: AsyncClient):
    _, token, _ = await _provision_with_card(client)

    response = await client.post(
        "/cards",
        json={"design": "midnight", "type": "physical", "is_one_time": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


async def test_create_physical_card_deducts_fee(client: AsyncClient):
    user_id, token, _ = await _provision_with_card(client)
    await client.post("/dev/fund", json={"amount_minor": 100_000}, headers={"Authorization": f"Bearer {token}"})

    response = await client.post(
        "/cards",
        json={"design": "graphite", "type": "physical", "pin": "1234"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    assert response.json()["type"] == "physical"

    account = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert account.json()["balance_minor"] == 100_000 - 2_000


async def test_create_physical_card_insufficient_funds(client: AsyncClient):
    _, token, _ = await _provision_with_card(client)  # sold 0

    response = await client.post(
        "/cards",
        json={"design": "graphite", "type": "physical", "pin": "1234"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 409


async def test_reveal_card_requires_correct_pin(client: AsyncClient):
    """Vezi tests/test_cards.py pentru acoperirea completă a PIN-ului de
    card (creare, reveal, backfill) — testul ăsta rămâne aici doar ca
    parte a fluxului "Cardul meu" existent din acest fișier."""
    _, token, _ = await _provision_with_card(client)
    created = await client.post(
        "/cards",
        json={"design": "midnight", "type": "virtual", "pin": "7777"},
        headers={"Authorization": f"Bearer {token}"},
    )
    card_id = created.json()["id"]

    wrong = await client.post(
        f"/cards/{card_id}/reveal",
        json={"pin": "0000"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert wrong.status_code == 401

    correct = await client.post(
        f"/cards/{card_id}/reveal",
        json={"pin": "7777"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert correct.status_code == 200
    body = correct.json()
    assert len(body["pan"]) == 16
    assert len(body["cvv"]) == 3


async def test_reveal_card_rejects_both_pin_and_webauthn(client: AsyncClient):
    _, token, card_id = await _provision_with_card(client)

    response = await client.post(
        f"/cards/{card_id}/reveal",
        json={"pin": "1234", "webauthn_challenge_id": "abc", "webauthn_assertion": {"id": "x"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


async def test_reveal_card_rejects_neither_pin_nor_webauthn(client: AsyncClient):
    _, token, card_id = await _provision_with_card(client)

    response = await client.post(
        f"/cards/{card_id}/reveal",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


async def test_reveal_card_with_webauthn_assertion(client: AsyncClient, monkeypatch):
    _, token, card_id = await _provision_with_card(client)

    captured: dict = {}

    async def _fake_verify(user_id: str, card_id_arg: str, challenge_id: str, assertion: dict) -> bool:
        captured["card_id"] = card_id_arg
        captured["challenge_id"] = challenge_id
        captured["assertion"] = assertion
        return challenge_id == "good-challenge"

    monkeypatch.setattr(service_module, "_verify_webauthn_with_auth_service", _fake_verify)

    wrong = await client.post(
        f"/cards/{card_id}/reveal",
        json={"webauthn_challenge_id": "bad-challenge", "webauthn_assertion": {"id": "x"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert wrong.status_code == 401

    correct = await client.post(
        f"/cards/{card_id}/reveal",
        json={"webauthn_challenge_id": "good-challenge", "webauthn_assertion": {"id": "x"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert correct.status_code == 200
    body = correct.json()
    assert len(body["pan"]) == 16
    assert len(body["cvv"]) == 3
    # card_id trimis către auth-service e cel REZOLVAT server-side (din URL),
    # nu unul pe care l-ar putea falsifica clientul — vezi
    # service.py::_verify_webauthn_with_auth_service.
    assert captured["card_id"] == card_id


async def test_provisioned_account_has_current_type(client: AsyncClient):
    _, body = await _provision(client)
    assert body["account"]["account_type"] == "current"


async def test_open_additional_account(client: AsyncClient):
    user_id, token = (await _provision_with_card(client))[:2]

    response = await client.post(
        "/new",
        json={"account_type": "savings"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["account_type"] == "savings"
    assert body["balance_minor"] == 0
    assert body["iban"].startswith("RO")

    all_accounts = await client.get("/all", headers={"Authorization": f"Bearer {token}"})
    assert all_accounts.status_code == 200
    types = {a["account_type"] for a in all_accounts.json()}
    assert types == {"current", "savings"}


async def test_cannot_open_duplicate_account_type(client: AsyncClient):
    _, token, _ = await _provision_with_card(client)

    first = await client.post("/new", json={"account_type": "deposit"}, headers={"Authorization": f"Bearer {token}"})
    assert first.status_code == 201

    second = await client.post("/new", json={"account_type": "deposit"}, headers={"Authorization": f"Bearer {token}"})
    assert second.status_code == 409


async def test_cannot_open_current_account_directly(client: AsyncClient):
    _, token, _ = await _provision_with_card(client)

    response = await client.post("/new", json={"account_type": "current"}, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 422  # "current" nu e în CreatableAccountType


async def test_new_account_does_not_affect_transfer_source(client: AsyncClient):
    """Contul folosit de transactions-service ca sursă de transfer rămâne
    STRICT contul curent, chiar și după deschiderea unui cont de economii."""
    user_id, token, _ = await _provision_with_card(client)
    await client.post("/new", json={"account_type": "student"}, headers={"Authorization": f"Bearer {token}"})

    from app.service import get_account_by_user

    resolved = await get_account_by_user(user_id)
    assert resolved.account_type == "current"


async def test_student_account_requires_document(client: AsyncClient):
    _, token, _ = await _provision_with_card(client)

    without_doc = await client.post("/new", json={"account_type": "student"}, headers={"Authorization": f"Bearer {token}"})
    assert without_doc.status_code == 422

    with_doc = await client.post(
        "/new",
        json={"account_type": "student", "document_filename": "adeverinta_student.pdf"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert with_doc.status_code == 201
    assert with_doc.json()["verification_document_name"] == "adeverinta_student.pdf"


async def test_savings_account_does_not_require_document(client: AsyncClient):
    _, token, _ = await _provision_with_card(client)

    response = await client.post("/new", json={"account_type": "savings"}, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 201
    assert response.json()["verification_document_name"] is None


async def test_cannot_delete_current_account(client: AsyncClient):
    user_id, token, _ = await _provision_with_card(client)
    account = await client.get("/me", headers={"Authorization": f"Bearer {token}"})

    response = await client.delete(f"/{account.json()['id']}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 400


async def test_cannot_delete_account_with_balance(client: AsyncClient):
    _, token, _ = await _provision_with_card(client)
    created = await client.post("/new", json={"account_type": "savings"}, headers={"Authorization": f"Bearer {token}"})
    account_id = created.json()["id"]

    db = get_database()
    await db.accounts.update_one({"_id": ObjectId(account_id)}, {"$set": {"balance_minor": 5000}})

    response = await client.delete(f"/{account_id}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 409


async def test_delete_empty_additional_account(client: AsyncClient):
    _, token, _ = await _provision_with_card(client)
    created = await client.post("/new", json={"account_type": "deposit"}, headers={"Authorization": f"Bearer {token}"})
    account_id = created.json()["id"]

    response = await client.delete(f"/{account_id}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 204

    all_accounts = await client.get("/all", headers={"Authorization": f"Bearer {token}"})
    types = {a["account_type"] for a in all_accounts.json()}
    assert "deposit" not in types


async def test_cannot_delete_another_users_account(client: AsyncClient):
    _, token, _ = await _provision_with_card(client)
    created = await client.post("/new", json={"account_type": "savings"}, headers={"Authorization": f"Bearer {token}"})
    account_id = created.json()["id"]

    other_user_id, _ = await _provision(client)
    other_token = _make_token(other_user_id)

    response = await client.delete(f"/{account_id}", headers={"Authorization": f"Bearer {other_token}"})
    assert response.status_code == 404


async def test_beneficiary_crud_and_isolation(client: AsyncClient):
    user_id, token = (await _provision_with_card(client))[:2]
    other_user_id, _ = await _provision(client)
    other_token = _make_token(other_user_id)

    create_response = await client.post(
        "/beneficiaries",
        json={"name": "Ana Popescu", "iban": "RO49MAES1234567890123456"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_response.status_code == 201
    beneficiary_id = create_response.json()["id"]

    mine = await client.get("/beneficiaries", headers={"Authorization": f"Bearer {token}"})
    assert mine.status_code == 200
    assert len(mine.json()) == 1
    assert mine.json()[0]["name"] == "Ana Popescu"

    others = await client.get("/beneficiaries", headers={"Authorization": f"Bearer {other_token}"})
    assert others.status_code == 200
    assert others.json() == []

    forbidden_delete = await client.delete(
        f"/beneficiaries/{beneficiary_id}", headers={"Authorization": f"Bearer {other_token}"}
    )
    assert forbidden_delete.status_code == 404

    own_delete = await client.delete(f"/beneficiaries/{beneficiary_id}", headers={"Authorization": f"Bearer {token}"})
    assert own_delete.status_code == 204


# --- GET /internal/accounts/{account_id}/for-user/{user_id} ----------------
# Folosit de transactions-service pentru extrasul de cont per-cont (vezi
# generate_account_statement) — userul alege ORICE cont al lui, nu doar
# "current". Reutilizează EXACT service.get_account_by_id_for_user, care
# există deja pentru ruta PUBLICĂ GET /accounts/{account_id} — testăm aici
# doar wiring-ul rutei /internal/, comportamentul funcției e deja acoperit
# mai jos (secțiunea "GET /accounts/{account_id}").


async def test_get_account_by_id_for_user_returns_own_account(client: AsyncClient):
    user_id, provisioned = await _provision(client)
    account_id = provisioned["account"]["_id"]
    response = await client.get(f"/internal/accounts/{account_id}/for-user/{user_id}")
    assert response.status_code == 200
    assert response.json()["id"] == account_id
    assert response.json()["account_type"] == "current"


async def test_get_account_by_id_for_user_rejects_other_users_account(client: AsyncClient):
    _, provisioned = await _provision(client)
    account_id = provisioned["account"]["_id"]
    other_user_id = str(ObjectId())
    response = await client.get(f"/internal/accounts/{account_id}/for-user/{other_user_id}")
    assert response.status_code == 404


# --- GET /accounts/{account_id} (rută publică) ------------------------------
# Regresie: exista deja o funcție `get_account_by_id_for_user` (service.py)
# folosită de ruta asta — o coliziune de nume în timpul dezvoltării
# extrasului de cont a suprascris-o temporar cu alta, incompatibilă ca
# response_model (lipseau `balance`/`created_at`), rupând ruta publică cu
# 500 fără ca vreun test existent s-o prindă. Fixat prin redenumire (vezi
# app/routers/internal.py::get_account_by_id_internal), dar rămâne
# netestată direct înainte de asta — acoperim golul aici.


async def test_get_account_by_id_public_route_returns_full_account(client: AsyncClient):
    user_id, provisioned = await _provision(client)
    account_id = provisioned["account"]["_id"]
    # NOTĂ: routers/accounts.py n-are prefix propriu — devine "/accounts"
    # DOAR prin Gateway (/api/accounts/...); direct pe app, ruta e "/{id}"
    # la rădăcină, la fel ca restul testelor din acest fișier ("/me", "/all"...).
    response = await client.get(f"/{account_id}", headers={"Authorization": f"Bearer {_make_token(user_id)}"})
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == account_id
    assert "balance" in body
    assert "created_at" in body


async def test_get_account_by_id_public_route_rejects_other_users_account(client: AsyncClient):
    _, provisioned = await _provision(client)
    account_id = provisioned["account"]["_id"]
    other_user_id = str(ObjectId())
    response = await client.get(f"/{account_id}", headers={"Authorization": f"Bearer {_make_token(other_user_id)}"})
    assert response.status_code == 404


# --- Primitive generice (debit/credit UN cont, rezolvare cont per user+tip)
# folosite de deposits-service (și, mai târziu, de un eventual serviciu de
# investiții) — vezi app/service.py::debit_account / credit_account /
# get_account_by_user_and_type.


async def test_debit_account_succeeds_with_sufficient_funds(client: AsyncClient):
    user_id, provisioned = await _provision(client)
    account_id = provisioned["account"]["_id"]
    await client.post("/dev/fund", json={"amount_minor": 100_000}, headers={"Authorization": f"Bearer {_make_token(user_id)}"})

    response = await client.post(f"/internal/accounts/{account_id}/debit", json={"amount_minor": 30_000})
    assert response.status_code == 200
    assert response.json()["balance_minor"] == 70_000


async def test_debit_account_rejects_insufficient_funds(client: AsyncClient):
    user_id, provisioned = await _provision(client)
    account_id = provisioned["account"]["_id"]

    response = await client.post(f"/internal/accounts/{account_id}/debit", json={"amount_minor": 500_000})
    assert response.status_code == 409


async def test_debit_account_rejects_invalid_id(client: AsyncClient):
    response = await client.post("/internal/accounts/not-an-object-id/debit", json={"amount_minor": 100})
    assert response.status_code == 400


async def test_credit_account_succeeds(client: AsyncClient):
    _, provisioned = await _provision(client)
    account_id = provisioned["account"]["_id"]

    response = await client.post(f"/internal/accounts/{account_id}/credit", json={"amount_minor": 25_000})
    assert response.status_code == 200
    assert response.json()["balance_minor"] == 25_000


async def test_credit_account_rejects_unknown_account(client: AsyncClient):
    response = await client.post(f"/internal/accounts/{ObjectId()}/credit", json={"amount_minor": 1_000})
    assert response.status_code == 404


async def test_get_account_by_user_and_type_returns_current(client: AsyncClient):
    user_id, provisioned = await _provision(client)
    account_id = provisioned["account"]["_id"]

    response = await client.get(f"/internal/accounts/by-user-and-type/{user_id}/current")
    assert response.status_code == 200
    assert response.json()["id"] == account_id
    assert response.json()["account_type"] == "current"


async def test_get_account_by_user_and_type_404_when_missing(client: AsyncClient):
    user_id, _ = await _provision(client)

    response = await client.get(f"/internal/accounts/by-user-and-type/{user_id}/eur")
    assert response.status_code == 404
