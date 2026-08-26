"""
Teste pentru auth-service.

Rulare (cu stack-ul pornit prin `docker compose up`, folosind o bază de
TEST separată, ca să nu polueze datele demo reale din auth_db):

    docker compose exec auth-service pip install pytest==8.3.3 pytest-asyncio==0.24.0 -q
    docker compose exec -e MONGO_URL=mongodb://mongodb:27017/auth_db_test auth-service python -m pytest -q

Provizionarea contului bancar (apel către accounts-service) este mock-uită
aici — nu e responsabilitatea acestui serviciu să testeze accounts-service,
iar altfel testele ar crea conturi reale în accounts_db la fiecare rulare.
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient
from webauthn import base64url_to_bytes

from app.config import settings
from app.database import get_database
from app.main import app
from app.security import hash_password
from webauthn_test_authenticator import SoftwareAuthenticator, b64url

pytestmark = pytest.mark.asyncio

VALID_PAYLOAD = {
    "first_name": "Octavia",
    "last_name": "Test",
    "email": "octavia.autotest@maestrobank.local",
    "phone_number": "+40711111111",
    "password": "Test1234!",
}


@pytest.fixture(autouse=True)
def mock_provisioning(monkeypatch):
    async def _noop(user_id: str) -> None:
        return None

    monkeypatch.setattr("app.service._provision_bank_account", _noop)


@pytest.fixture(autouse=True)
async def clean_users_collection():
    await get_database().users.delete_many({})
    yield
    await get_database().users.delete_many({})


@pytest.fixture(autouse=True)
async def clean_webauthn_collections():
    await get_database().webauthn_credentials.delete_many({})
    await get_database().webauthn_challenges.delete_many({})
    yield
    await get_database().webauthn_credentials.delete_many({})
    await get_database().webauthn_challenges.delete_many({})


@pytest.fixture(autouse=True)
async def clean_login_events_collection():
    await get_database().login_events.delete_many({})
    yield
    await get_database().login_events.delete_many({})


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_register_creates_user(client: AsyncClient):
    response = await client.post("/auth/register", json=VALID_PAYLOAD)
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == VALID_PAYLOAD["email"]
    assert body["first_name"] == VALID_PAYLOAD["first_name"]
    assert "password_hash" not in body
    assert "password" not in body


async def test_register_duplicate_email_rejected(client: AsyncClient):
    first = await client.post("/auth/register", json=VALID_PAYLOAD)
    assert first.status_code == 201

    second = await client.post("/auth/register", json=VALID_PAYLOAD)
    assert second.status_code == 409


async def test_internal_get_user_contact_returns_phone_and_email(client: AsyncClient):
    """Consumat de transactions-service/app/holds.py — lista de personal
    are nevoie de datele de contact ca să sune clientul."""
    register_response = await client.post("/auth/register", json=VALID_PAYLOAD)
    user_id = register_response.json()["id"]

    response = await client.get(f"/internal/users/{user_id}/contact")
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == VALID_PAYLOAD["email"]
    assert body["phone_number"] == VALID_PAYLOAD["phone_number"]
    assert body["first_name"] == VALID_PAYLOAD["first_name"]


async def test_internal_get_user_contact_404_for_unknown_user(client: AsyncClient):
    response = await client.get(f"/internal/users/{ObjectId()}/contact")
    assert response.status_code == 404


async def test_register_rejects_malformed_phone_number(client: AsyncClient):
    response = await client.post("/auth/register", json={**VALID_PAYLOAD, "phone_number": "not-a-phone!"})
    assert response.status_code == 422


async def test_register_rejects_missing_phone_number(client: AsyncClient):
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "phone_number"}
    response = await client.post("/auth/register", json=payload)
    assert response.status_code == 422


async def test_me_includes_phone_number(client: AsyncClient):
    token = await _register_and_login(client)
    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.json()["phone_number"] == VALID_PAYLOAD["phone_number"]


async def test_login_valid(client: AsyncClient):
    await client.post("/auth/register", json=VALID_PAYLOAD)

    response = await client.post(
        "/auth/login",
        json={"email": VALID_PAYLOAD["email"], "password": VALID_PAYLOAD["password"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


async def test_login_wrong_password_rejected(client: AsyncClient):
    await client.post("/auth/register", json=VALID_PAYLOAD)

    response = await client.post(
        "/auth/login",
        json={"email": VALID_PAYLOAD["email"], "password": "ParolaGresita1"},
    )
    assert response.status_code == 401


async def test_me_without_jwt_rejected(client: AsyncClient):
    response = await client.get("/auth/me")
    assert response.status_code == 401


async def test_me_with_valid_jwt(client: AsyncClient):
    await client.post("/auth/register", json=VALID_PAYLOAD)
    login_response = await client.post(
        "/auth/login",
        json={"email": VALID_PAYLOAD["email"], "password": VALID_PAYLOAD["password"]},
    )
    token = login_response.json()["access_token"]

    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == VALID_PAYLOAD["email"]


async def _register_and_login(client: AsyncClient) -> str:
    await client.post("/auth/register", json=VALID_PAYLOAD)
    login_response = await client.post(
        "/auth/login",
        json={"email": VALID_PAYLOAD["email"], "password": VALID_PAYLOAD["password"]},
    )
    return login_response.json()["access_token"]


async def test_change_password_without_jwt_rejected(client: AsyncClient):
    response = await client.post(
        "/auth/change-password",
        json={"current_password": VALID_PAYLOAD["password"], "new_password": "NewPass1234"},
    )
    assert response.status_code == 401


async def test_change_password_wrong_current_password_rejected(client: AsyncClient):
    token = await _register_and_login(client)

    response = await client.post(
        "/auth/change-password",
        json={"current_password": "NotTheRealPassword1", "new_password": "NewPass1234"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


async def test_change_password_weak_new_password_rejected(client: AsyncClient):
    token = await _register_and_login(client)

    response = await client.post(
        "/auth/change-password",
        json={"current_password": VALID_PAYLOAD["password"], "new_password": "onlyletters"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


async def test_change_password_success_allows_login_with_new_password(client: AsyncClient):
    token = await _register_and_login(client)

    response = await client.post(
        "/auth/change-password",
        json={"current_password": VALID_PAYLOAD["password"], "new_password": "NewPass1234"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 204

    old_login = await client.post(
        "/auth/login",
        json={"email": VALID_PAYLOAD["email"], "password": VALID_PAYLOAD["password"]},
    )
    assert old_login.status_code == 401

    new_login = await client.post(
        "/auth/login",
        json={"email": VALID_PAYLOAD["email"], "password": "NewPass1234"},
    )
    assert new_login.status_code == 200


# --- WebAuthn / passkeys ---------------------------------------------------


async def _register_passkey(client: AsyncClient, token: str, authenticator: SoftwareAuthenticator) -> None:
    options_resp = await client.post("/auth/webauthn/register/options", headers={"Authorization": f"Bearer {token}"})
    assert options_resp.status_code == 200
    body = options_resp.json()

    credential = authenticator.create(
        challenge=base64url_to_bytes(body["options"]["challenge"]),
        rp_id=settings.webauthn_rp_id,
        origin=settings.webauthn_origins[0],
    )
    verify_resp = await client.post(
        "/auth/webauthn/register/verify",
        json={"challenge_id": body["challenge_id"], "credential": credential},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert verify_resp.status_code == 201


async def _login_options(client: AsyncClient, email: str) -> tuple[str, dict]:
    resp = await client.post("/auth/webauthn/login/options", json={"email": email})
    assert resp.status_code == 200
    body = resp.json()
    return body["challenge_id"], body["options"]


async def test_webauthn_register_and_login_round_trip(client: AsyncClient):
    token = await _register_and_login(client)
    authenticator = SoftwareAuthenticator()
    await _register_passkey(client, token, authenticator)

    challenge_id, options = await _login_options(client, VALID_PAYLOAD["email"])
    credential = authenticator.get(
        challenge=base64url_to_bytes(options["challenge"]),
        rp_id=settings.webauthn_rp_id,
        origin=settings.webauthn_origins[0],
    )

    verify_resp = await client.post("/auth/webauthn/login/verify", json={"challenge_id": challenge_id, "credential": credential})
    assert verify_resp.status_code == 200
    assert "access_token" in verify_resp.json()


async def test_webauthn_replayed_challenge_rejected(client: AsyncClient):
    token = await _register_and_login(client)
    authenticator = SoftwareAuthenticator()
    await _register_passkey(client, token, authenticator)

    challenge_id, options = await _login_options(client, VALID_PAYLOAD["email"])
    credential = authenticator.get(
        challenge=base64url_to_bytes(options["challenge"]), rp_id=settings.webauthn_rp_id, origin=settings.webauthn_origins[0]
    )

    first = await client.post("/auth/webauthn/login/verify", json={"challenge_id": challenge_id, "credential": credential})
    assert first.status_code == 200

    second = await client.post("/auth/webauthn/login/verify", json={"challenge_id": challenge_id, "credential": credential})
    assert second.status_code == 400


async def test_webauthn_expired_challenge_rejected(client: AsyncClient):
    token = await _register_and_login(client)
    authenticator = SoftwareAuthenticator()
    await _register_passkey(client, token, authenticator)

    challenge_id, options = await _login_options(client, VALID_PAYLOAD["email"])
    credential = authenticator.get(
        challenge=base64url_to_bytes(options["challenge"]), rp_id=settings.webauthn_rp_id, origin=settings.webauthn_origins[0]
    )

    await get_database().webauthn_challenges.update_one(
        {"_id": ObjectId(challenge_id)},
        {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}},
    )

    resp = await client.post("/auth/webauthn/login/verify", json={"challenge_id": challenge_id, "credential": credential})
    assert resp.status_code == 400


async def test_webauthn_wrong_origin_rejected(client: AsyncClient):
    token = await _register_and_login(client)
    authenticator = SoftwareAuthenticator()
    await _register_passkey(client, token, authenticator)

    challenge_id, options = await _login_options(client, VALID_PAYLOAD["email"])
    credential = authenticator.get(
        challenge=base64url_to_bytes(options["challenge"]), rp_id=settings.webauthn_rp_id, origin="http://evil.example"
    )

    resp = await client.post("/auth/webauthn/login/verify", json={"challenge_id": challenge_id, "credential": credential})
    assert resp.status_code == 401


async def test_webauthn_wrong_rp_id_rejected(client: AsyncClient):
    token = await _register_and_login(client)
    authenticator = SoftwareAuthenticator()
    await _register_passkey(client, token, authenticator)

    challenge_id, options = await _login_options(client, VALID_PAYLOAD["email"])
    credential = authenticator.get(
        challenge=base64url_to_bytes(options["challenge"]), rp_id="not-the-real-rp-id", origin=settings.webauthn_origins[0]
    )

    resp = await client.post("/auth/webauthn/login/verify", json={"challenge_id": challenge_id, "credential": credential})
    assert resp.status_code == 401


async def test_webauthn_tampered_signature_rejected(client: AsyncClient):
    token = await _register_and_login(client)
    authenticator = SoftwareAuthenticator()
    await _register_passkey(client, token, authenticator)

    challenge_id, options = await _login_options(client, VALID_PAYLOAD["email"])
    credential = authenticator.get(
        challenge=base64url_to_bytes(options["challenge"]), rp_id=settings.webauthn_rp_id, origin=settings.webauthn_origins[0]
    )

    tampered = bytearray(base64url_to_bytes(credential["response"]["signature"]))
    tampered[0] ^= 0xFF
    credential["response"]["signature"] = b64url(bytes(tampered))

    resp = await client.post("/auth/webauthn/login/verify", json={"challenge_id": challenge_id, "credential": credential})
    assert resp.status_code == 401


async def test_webauthn_missing_user_verification_rejected(client: AsyncClient):
    token = await _register_and_login(client)
    authenticator = SoftwareAuthenticator()
    await _register_passkey(client, token, authenticator)

    challenge_id, options = await _login_options(client, VALID_PAYLOAD["email"])
    credential = authenticator.get(
        challenge=base64url_to_bytes(options["challenge"]),
        rp_id=settings.webauthn_rp_id,
        origin=settings.webauthn_origins[0],
        user_verified=False,
    )

    resp = await client.post("/auth/webauthn/login/verify", json={"challenge_id": challenge_id, "credential": credential})
    assert resp.status_code == 401


async def test_webauthn_sign_count_regression_rejected(client: AsyncClient):
    """Detectare de clonare: un assertion "vechi" (contor mai mic decât cel
    deja stocat) trebuie respins, iar credențiala revocată automat."""
    token = await _register_and_login(client)
    authenticator = SoftwareAuthenticator()
    await _register_passkey(client, token, authenticator)

    # assertion #1 (contor=1) — capturat, dar NU trimis încă
    stale_challenge_id, stale_options = await _login_options(client, VALID_PAYLOAD["email"])
    stale_credential = authenticator.get(
        challenge=base64url_to_bytes(stale_options["challenge"]), rp_id=settings.webauthn_rp_id, origin=settings.webauthn_origins[0]
    )

    # assertion #2 (contor=2) — trimis imediat, avansează contorul stocat la 2
    fresh_challenge_id, fresh_options = await _login_options(client, VALID_PAYLOAD["email"])
    fresh_credential = authenticator.get(
        challenge=base64url_to_bytes(fresh_options["challenge"]), rp_id=settings.webauthn_rp_id, origin=settings.webauthn_origins[0]
    )
    fresh_resp = await client.post("/auth/webauthn/login/verify", json={"challenge_id": fresh_challenge_id, "credential": fresh_credential})
    assert fresh_resp.status_code == 200

    # acum retrimitem assertion-ul VECHI (contor=1, sub cel stocat=2)
    stale_resp = await client.post("/auth/webauthn/login/verify", json={"challenge_id": stale_challenge_id, "credential": stale_credential})
    assert stale_resp.status_code == 401

    # credențiala a fost revocată automat — nu mai apare la listare
    creds = await client.get("/auth/webauthn/credentials", headers={"Authorization": f"Bearer {token}"})
    assert creds.json() == []


async def test_webauthn_login_options_generic_for_unknown_email(client: AsyncClient):
    token = await _register_and_login(client)
    authenticator = SoftwareAuthenticator()
    await _register_passkey(client, token, authenticator)

    unknown = await client.post("/auth/webauthn/login/options", json={"email": "nu-exista@maestrobank.local"})
    known = await client.post("/auth/webauthn/login/options", json={"email": VALID_PAYLOAD["email"]})

    assert unknown.status_code == known.status_code == 200
    assert not unknown.json()["options"].get("allowCredentials")
    assert len(known.json()["options"].get("allowCredentials", [])) == 1


async def test_webauthn_credentials_scoped_to_owner(client: AsyncClient):
    token = await _register_and_login(client)
    authenticator = SoftwareAuthenticator()
    await _register_passkey(client, token, authenticator)

    creds = await client.get("/auth/webauthn/credentials", headers={"Authorization": f"Bearer {token}"})
    assert creds.status_code == 200
    assert len(creds.json()) == 1
    credential_id = creds.json()[0]["id"]

    other_payload = {**VALID_PAYLOAD, "email": "altcineva.autotest@maestrobank.local"}
    await client.post("/auth/register", json=other_payload)
    other_login = await client.post("/auth/login", json={"email": other_payload["email"], "password": other_payload["password"]})
    other_token = other_login.json()["access_token"]

    forbidden = await client.delete(f"/auth/webauthn/credentials/{credential_id}", headers={"Authorization": f"Bearer {other_token}"})
    assert forbidden.status_code == 404

    own_delete = await client.delete(f"/auth/webauthn/credentials/{credential_id}", headers={"Authorization": f"Bearer {token}"})
    assert own_delete.status_code == 204


async def test_webauthn_stepup_requires_jwt(client: AsyncClient):
    resp = await client.post("/auth/webauthn/stepup/options", json={"action": "card_reveal", "action_payload": "abc123"})
    assert resp.status_code == 401


async def test_internal_verify_webauthn_rejects_mismatched_action_payload(client: AsyncClient):
    """Dovedește legarea challenge-ului de step-up la o acțiune EXACTĂ: un
    assertion valid pentru "card-A" nu poate fi refolosit pentru "card-B"."""
    token = await _register_and_login(client)
    authenticator = SoftwareAuthenticator()
    await _register_passkey(client, token, authenticator)

    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    user_id = me.json()["id"]

    stepup = await client.post(
        "/auth/webauthn/stepup/options",
        json={"action": "card_reveal", "action_payload": "card-A"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert stepup.status_code == 200
    challenge_id = stepup.json()["challenge_id"]
    credential = authenticator.get(
        challenge=base64url_to_bytes(stepup.json()["options"]["challenge"]),
        rp_id=settings.webauthn_rp_id,
        origin=settings.webauthn_origins[0],
    )

    mismatched = await client.post(
        "/internal/auth/verify-webauthn",
        json={
            "user_id": user_id,
            "challenge_id": challenge_id,
            "action": "card_reveal",
            "action_payload": "card-B",
            "credential": credential,
        },
    )
    assert mismatched.status_code == 200
    assert mismatched.json()["valid"] is False


async def test_internal_verify_webauthn_succeeds_for_matching_payload(client: AsyncClient):
    token = await _register_and_login(client)
    authenticator = SoftwareAuthenticator()
    await _register_passkey(client, token, authenticator)

    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    user_id = me.json()["id"]

    stepup = await client.post(
        "/auth/webauthn/stepup/options",
        json={"action": "card_reveal", "action_payload": "card-A"},
        headers={"Authorization": f"Bearer {token}"},
    )
    challenge_id = stepup.json()["challenge_id"]
    credential = authenticator.get(
        challenge=base64url_to_bytes(stepup.json()["options"]["challenge"]),
        rp_id=settings.webauthn_rp_id,
        origin=settings.webauthn_origins[0],
    )

    matched = await client.post(
        "/internal/auth/verify-webauthn",
        json={
            "user_id": user_id,
            "challenge_id": challenge_id,
            "action": "card_reveal",
            "action_payload": "card-A",
            "credential": credential,
        },
    )
    assert matched.status_code == 200
    assert matched.json()["valid"] is True


# --- Roluri de personal (role="staff" în JWT) ------------------------------
#
# UserRegister nu are câmp "role" (vezi app/models.py) — un client nu poate
# NICIODATĂ cere rolul "staff" prin înregistrare publică. Singura cale spre
# role="staff" e o scriere directă în Mongo (scripts/create_staff_user.py,
# reprodusă aici prin _seed_staff_user, la fel cum alte teste din acest
# fișier scriu direct în colecții pentru scenarii pe care API-ul public nu
# le poate produce).


async def test_register_always_yields_customer_role(client: AsyncClient):
    token = await _register_and_login(client)
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    assert payload["role"] == "customer"

    me_resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.json()["role"] == "customer"


async def _seed_staff_user(email: str, password: str) -> None:
    await get_database().users.insert_one(
        {
            "first_name": "Staff",
            "last_name": "Test",
            "email": email,
            "password_hash": hash_password(password),
            "created_at": datetime.now(timezone.utc),
            "is_active": True,
            "role": "staff",
        }
    )


async def test_staff_role_included_in_password_login_jwt(client: AsyncClient):
    email, password = "staff.autotest@maestrobank.local", "StaffPass123"
    await _seed_staff_user(email, password)

    response = await client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200

    payload = jwt.decode(response.json()["access_token"], settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    assert payload["role"] == "staff"


async def test_staff_role_included_in_webauthn_login_jwt(client: AsyncClient):
    """Ambele căi de autentificare converg pe create_access_token — vezi
    app/webauthn_service.py — deci rolul trebuie să apară identic indiferent
    de metodă (parolă sau passkey)."""
    email, password = "staff.webauthn.autotest@maestrobank.local", "StaffPass123"
    await _seed_staff_user(email, password)

    password_token = (await client.post("/auth/login", json={"email": email, "password": password})).json()["access_token"]
    authenticator = SoftwareAuthenticator()
    await _register_passkey(client, password_token, authenticator)

    challenge_id, options = await _login_options(client, email)
    credential = authenticator.get(
        challenge=base64url_to_bytes(options["challenge"]),
        rp_id=settings.webauthn_rp_id,
        origin=settings.webauthn_origins[0],
    )
    verify_resp = await client.post(
        "/auth/webauthn/login/verify", json={"challenge_id": challenge_id, "credential": credential}
    )
    assert verify_resp.status_code == 200

    payload = jwt.decode(
        verify_resp.json()["access_token"], settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )
    assert payload["role"] == "staff"


# --- Login events / device tracking / geolocation (VEL-04, DEV-0x) --------
#
# Nu testăm geoip.py aici (IP-urile de test sunt loopback -> geolocalizare
# sărită din start, vezi app/geoip.py) — doar CĂ un login_events e scris,
# cu user_id/success corecte, indiferent de rezultatul geolocalizării.


async def test_login_success_records_login_event(client: AsyncClient):
    register_response = await client.post("/auth/register", json=VALID_PAYLOAD)
    user_id = register_response.json()["id"]

    await client.post("/auth/login", json={"email": VALID_PAYLOAD["email"], "password": VALID_PAYLOAD["password"]})

    events = await get_database().login_events.find({"user_id": user_id}).to_list(length=10)
    assert len(events) == 1
    assert events[0]["success"] is True
    assert events[0]["email_attempted"] == VALID_PAYLOAD["email"]


async def test_login_wrong_password_records_failed_event(client: AsyncClient):
    register_response = await client.post("/auth/register", json=VALID_PAYLOAD)
    user_id = register_response.json()["id"]

    await client.post("/auth/login", json={"email": VALID_PAYLOAD["email"], "password": "ParolaGresita1"})

    events = await get_database().login_events.find({"user_id": user_id}).to_list(length=10)
    assert len(events) == 1
    assert events[0]["success"] is False


async def test_login_unknown_email_records_event_without_user_id(client: AsyncClient):
    unknown_email = "nu-exista-deloc@maestrobank.local"
    await client.post("/auth/login", json={"email": unknown_email, "password": "OricePassword1"})

    events = await get_database().login_events.find({"email_attempted": unknown_email}).to_list(length=10)
    assert len(events) == 1
    assert events[0]["success"] is False
    assert events[0]["user_id"] is None


async def test_webauthn_login_success_records_login_event(client: AsyncClient):
    token = await _register_and_login(client)
    authenticator = SoftwareAuthenticator()
    await _register_passkey(client, token, authenticator)

    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    user_id = me.json()["id"]
    await get_database().login_events.delete_many({"user_id": user_id})  # curăță evenimentul de la _register_and_login

    challenge_id, options = await _login_options(client, VALID_PAYLOAD["email"])
    credential = authenticator.get(
        challenge=base64url_to_bytes(options["challenge"]), rp_id=settings.webauthn_rp_id, origin=settings.webauthn_origins[0]
    )
    verify_resp = await client.post("/auth/webauthn/login/verify", json={"challenge_id": challenge_id, "credential": credential})
    assert verify_resp.status_code == 200

    events = await get_database().login_events.find({"user_id": user_id}).to_list(length=10)
    assert len(events) == 1
    assert events[0]["success"] is True


async def test_change_password_sets_password_changed_at(client: AsyncClient):
    register_response = await client.post("/auth/register", json=VALID_PAYLOAD)
    user_id = register_response.json()["id"]

    before = await get_database().users.find_one({"_id": ObjectId(user_id)})
    assert before.get("password_changed_at") is None

    token = (
        await client.post("/auth/login", json={"email": VALID_PAYLOAD["email"], "password": VALID_PAYLOAD["password"]})
    ).json()["access_token"]
    response = await client.post(
        "/auth/change-password",
        json={"current_password": VALID_PAYLOAD["password"], "new_password": "NewPass1234"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 204

    after = await get_database().users.find_one({"_id": ObjectId(user_id)})
    assert after["password_changed_at"] is not None


async def test_webauthn_revoke_is_soft_delete_not_hard_delete(client: AsyncClient):
    """revoke_credential trebuie să scrie `revoked_at`, NU să șteargă
    documentul — DEV-02 (fraud, transactions-service) are nevoie să vadă
    revocarea prin /internal/security-facts. Vezi webauthn_service.py."""
    token = await _register_and_login(client)
    authenticator = SoftwareAuthenticator()
    await _register_passkey(client, token, authenticator)

    creds = await client.get("/auth/webauthn/credentials", headers={"Authorization": f"Bearer {token}"})
    credential_id = creds.json()[0]["id"]

    delete_resp = await client.delete(f"/auth/webauthn/credentials/{credential_id}", headers={"Authorization": f"Bearer {token}"})
    assert delete_resp.status_code == 204

    # documentul TOT există în DB, doar marcat revocat
    stored = await get_database().webauthn_credentials.find_one({"_id": ObjectId(credential_id)})
    assert stored is not None
    assert stored["revoked_at"] is not None

    # dar dispare din orice listare/verificare activă, exact ca înainte
    after_list = await client.get("/auth/webauthn/credentials", headers={"Authorization": f"Bearer {token}"})
    assert after_list.json() == []


async def test_internal_security_facts_combines_logins_password_and_credential_events(client: AsyncClient):
    register_response = await client.post("/auth/register", json=VALID_PAYLOAD)
    user_id = register_response.json()["id"]

    # succes + eșec, ambele urmărite
    token = (
        await client.post("/auth/login", json={"email": VALID_PAYLOAD["email"], "password": VALID_PAYLOAD["password"]})
    ).json()["access_token"]
    await client.post("/auth/login", json={"email": VALID_PAYLOAD["email"], "password": "GresitaCuTotul1"})

    # schimbare parolă -> password_changed_at
    await client.post(
        "/auth/change-password",
        json={"current_password": VALID_PAYLOAD["password"], "new_password": "NewPass1234"},
        headers={"Authorization": f"Bearer {token}"},
    )

    # înrolare + revocare passkey -> evenimente de credențială
    authenticator = SoftwareAuthenticator()
    await _register_passkey(client, token, authenticator)
    creds = await client.get("/auth/webauthn/credentials", headers={"Authorization": f"Bearer {token}"})
    credential_id = creds.json()[0]["id"]
    await client.delete(f"/auth/webauthn/credentials/{credential_id}", headers={"Authorization": f"Bearer {token}"})

    response = await client.get(f"/internal/security-facts/{user_id}")
    assert response.status_code == 200
    body = response.json()

    assert len(body["recent_logins"]) == 2
    successes = [e["success"] for e in body["recent_logins"]]
    assert True in successes and False in successes

    assert body["password_changed_at"] is not None

    events = {e["event"] for e in body["recent_credential_events"]}
    assert events == {"enrolled", "revoked"}
