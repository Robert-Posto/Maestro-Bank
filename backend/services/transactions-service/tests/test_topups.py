"""Teste pentru reîncărcarea telefonică (POST /transactions/topups,
app/service.py::create_topup / _get_topup_merchant_iban).

create_topup e un wrapper subțire peste create_transfer (vezi
test_transfers.py) — rezolvă IBAN-ul contului-pseudo al operatorului, apoi
delegă total logica de bani (motor de fraudă, content screening, creare
tranzacție) către create_transfer, deja testată separat. Testele de-aici
verifică DOAR partea nouă: rezolvarea operatorului și validarea payload-ului.

_get_topup_merchant_iban (apelul HTTP către accounts-service) e mock-uit
direct — nu reluăm testele de merchant accounts de-acolo (au propriile
teste în accounts-service/tests/test_topup_merchant_accounts.py).
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from bson import ObjectId
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import get_database
from app.main import app

pytestmark = pytest.mark.asyncio

USER_ID = str(ObjectId())
SOURCE_ACCOUNT_ID = str(ObjectId())
MERCHANT_ACCOUNT_ID = str(ObjectId())

SOURCE_ACCOUNT = {
    "id": SOURCE_ACCOUNT_ID,
    "user_id": USER_ID,
    "iban": "RO11MAES0000000000000001",
    "currency": "RON",
    "balance_minor": 100_000,
    "status": "active",
}

MERCHANT_ACCOUNT = {
    "id": MERCHANT_ACCOUNT_ID,
    "user_id": "merchant:topup-orange",
    "iban": "RO99MAESTOPUPORANGE00001",
    "currency": "RON",
    "balance_minor": 0,
    "status": "active",
}


def _make_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "email": "test@example.com", "iat": now, "exp": now + timedelta(minutes=30)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


AUTH_HEADER = {"Authorization": f"Bearer {_make_token(USER_ID)}"}


@pytest.fixture(autouse=True)
async def clean_transactions():
    await get_database().transactions.delete_many({})
    yield
    await get_database().transactions.delete_many({})


@pytest.fixture(autouse=True)
def _twilio_not_configured_by_default(monkeypatch):
    """Izolăm complet de starea ambientală — dacă `.env` local are chei
    Twilio reale (ex. dezvoltare cu integrarea deja activată), testele NU
    trebuie să depindă de asta și cu atât mai puțin să facă apeluri reale
    (plătite) către Twilio. Testele care chiar vor calea "configurat"
    folosesc fixture-ul `twilio_configured` de mai jos, care rulează DUPĂ
    acesta (autouse rulează primul) și suprascrie explicit valorile."""
    monkeypatch.setattr(settings, "twilio_account_sid", "")
    monkeypatch.setattr(settings, "twilio_auth_token", "")


@pytest.fixture
def mock_accounts(monkeypatch):
    """Aceleași mock-uri de bază ca test_transfers.py (create_topup
    delegă la create_transfer), plus _get_topup_merchant_iban, care
    rezolvă direct la contul-pseudo Orange, fără apel HTTP real."""
    state = {"source": dict(SOURCE_ACCOUNT), "merchant": dict(MERCHANT_ACCOUNT)}

    async def fake_get_by_user(user_id: str) -> dict:
        return state["source"]

    async def fake_get_by_iban(iban: str):
        return state["merchant"]

    async def fake_apply_transfer(from_id: str, to_id: str, amount_minor: int) -> dict:
        state["source"]["balance_minor"] -= amount_minor
        state["merchant"]["balance_minor"] += amount_minor
        return {
            "from_balance_minor": state["source"]["balance_minor"],
            "to_balance_minor": state["merchant"]["balance_minor"],
        }

    async def fake_get_user_name(user_id: str) -> str | None:
        return "Orange" if user_id == "merchant:topup-orange" else "Client Test"

    async def fake_get_account_card_settings(account_id: str) -> dict:
        return {"transaction_alerts_enabled": True, "payment_confirmation_required": False, "payment_confirmation_card_id": None}

    async def fake_verify_card_pin(card_id: str, pin: str) -> bool:
        return False

    async def fake_get_topup_merchant_iban(operator: str) -> str:
        return state["merchant"]["iban"]

    monkeypatch.setattr("app.service._get_account_by_user", fake_get_by_user)
    monkeypatch.setattr("app.service._get_account_by_iban", fake_get_by_iban)
    monkeypatch.setattr("app.service._apply_transfer", fake_apply_transfer)
    monkeypatch.setattr("app.service._get_user_name", fake_get_user_name)
    monkeypatch.setattr("app.service._get_account_card_settings", fake_get_account_card_settings)
    monkeypatch.setattr("app.service._verify_card_pin", fake_verify_card_pin)
    monkeypatch.setattr("app.service._get_topup_merchant_iban", fake_get_topup_merchant_iban)
    return state


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_topup_succeeds(client: AsyncClient, mock_accounts):
    response = await client.post(
        "/transactions/topups",
        json={"operator": "orange", "phone_number": "0722334455", "amount_minor": 2_000},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert body["direction"] == "outgoing"
    assert body["amount_minor"] == 2_000
    assert body["counterparty_iban"] == MERCHANT_ACCOUNT["iban"]
    assert "Orange" in body["description"]
    assert "0722334455" in body["description"]
    assert mock_accounts["source"]["balance_minor"] == 98_000
    # Twilio neconfigurat în teste (TWILIO_ACCOUNT_SID/TOKEN implicit goale)
    # — verificarea trebuie să fie explicit vizibilă ca "neefectuată", nu
    # tăcută (vezi service.py::_verify_topup_phone).
    assert body["phone_verification"] == {
        "checked": False,
        "carrier_name": None,
        "line_type": None,
        "operator_match": None,
        "unavailable_reason": "not_configured",
    }
    assert body["content_warning"] is None


async def test_topup_rejects_unknown_operator(client: AsyncClient, mock_accounts):
    response = await client.post(
        "/transactions/topups",
        json={"operator": "lyca-mobile", "phone_number": "0722334455", "amount_minor": 2_000},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 422
    assert mock_accounts["source"]["balance_minor"] == 100_000


@pytest.mark.parametrize("phone_number", ["123", "07223344551", "0822334455", "072233445a"])
async def test_topup_rejects_invalid_phone_number(client: AsyncClient, mock_accounts, phone_number):
    response = await client.post(
        "/transactions/topups",
        json={"operator": "orange", "phone_number": phone_number, "amount_minor": 2_000},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 422
    assert mock_accounts["source"]["balance_minor"] == 100_000


async def test_topup_rejects_non_positive_amount(client: AsyncClient, mock_accounts):
    response = await client.post(
        "/transactions/topups",
        json={"operator": "orange", "phone_number": "0722334455", "amount_minor": 0},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 422


async def test_topup_rejects_amount_above_cap(client: AsyncClient, mock_accounts):
    response = await client.post(
        "/transactions/topups",
        json={"operator": "orange", "phone_number": "0722334455", "amount_minor": 100_001},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 422


async def test_topup_propagates_merchant_lookup_failure(client: AsyncClient, mock_accounts, monkeypatch):
    async def fake_get_topup_merchant_iban_failing(operator: str) -> str:
        raise HTTPException(status_code=502, detail="accounts-service indisponibil.")

    monkeypatch.setattr("app.service._get_topup_merchant_iban", fake_get_topup_merchant_iban_failing)

    response = await client.post(
        "/transactions/topups",
        json={"operator": "orange", "phone_number": "0722334455", "amount_minor": 2_000},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 502
    assert mock_accounts["source"]["balance_minor"] == 100_000


# --- Verificare Twilio Lookup (app/twilio_client.py, service.py::
# _verify_topup_phone) — twilio_client.lookup_carrier e mock-uit direct la
# graniță (aceeași convenție ca _get_topup_merchant_iban mai sus); nu
# refacem aici testele de apel HTTP către Twilio. ------------------------


@pytest.fixture
def twilio_configured(monkeypatch):
    """Simulează credențiale Twilio prezente — vezi config.py::
    twilio_configured (calculat din cele două de mai jos, nu o proprietate
    separat mock-uibilă)."""
    monkeypatch.setattr(settings, "twilio_account_sid", "ACtest")
    monkeypatch.setattr(settings, "twilio_auth_token", "secret")


async def test_topup_records_matching_operator_verification(client: AsyncClient, mock_accounts, twilio_configured, monkeypatch):
    from app import twilio_client

    async def fake_lookup_carrier(phone_e164: str):
        assert phone_e164 == "+40722334455"
        return twilio_client.CarrierLookupResult(carrier_name="Orange Romania", line_type="mobile")

    monkeypatch.setattr("app.service.twilio_client.lookup_carrier", fake_lookup_carrier)

    response = await client.post(
        "/transactions/topups",
        json={"operator": "orange", "phone_number": "0722334455", "amount_minor": 2_000},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["phone_verification"] == {
        "checked": True,
        "carrier_name": "Orange Romania",
        "line_type": "mobile",
        "operator_match": True,
        "unavailable_reason": None,
    }
    assert body["content_warning"] is None
    assert mock_accounts["source"]["balance_minor"] == 98_000


async def test_topup_operator_mismatch_requires_confirmation_before_moving_money(
    client: AsyncClient, mock_accounts, twilio_configured, monkeypatch
):
    """Nepotrivire de operator — spre deosebire de content_screening,
    reîncărcarea NU trece automat cu doar un avertisment: cere confirmare
    explicită (428, mirror pe card_pin/"Payment confirmation" la
    create_transfer) ÎNAINTE de a atinge banii."""
    from app import twilio_client

    async def fake_lookup_carrier(phone_e164: str):
        return twilio_client.CarrierLookupResult(carrier_name="Vodafone Romania", line_type="mobile")

    monkeypatch.setattr("app.service.twilio_client.lookup_carrier", fake_lookup_carrier)

    response = await client.post(
        "/transactions/topups",
        json={"operator": "orange", "phone_number": "0722334455", "amount_minor": 2_000},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 428
    assert "Vodafone Romania" in response.json()["detail"]
    # Blocat ÎNAINTE de orice mișcare de bani.
    assert mock_accounts["source"]["balance_minor"] == 100_000


async def test_topup_operator_mismatch_confirmed_still_succeeds_with_warning_on_record(
    client: AsyncClient, mock_accounts, twilio_configured, monkeypatch
):
    """Retrimiterea cu confirm_mismatch=True (exact fluxul frontend-ului
    după ce userul confirmă în dialog) trece — dar avertismentul rămâne pe
    tranzacție ca istoric, nu dispare doar fiindcă userul a ales să continue."""
    from app import twilio_client

    async def fake_lookup_carrier(phone_e164: str):
        return twilio_client.CarrierLookupResult(carrier_name="Vodafone Romania", line_type="mobile")

    monkeypatch.setattr("app.service.twilio_client.lookup_carrier", fake_lookup_carrier)

    response = await client.post(
        "/transactions/topups",
        json={"operator": "orange", "phone_number": "0722334455", "amount_minor": 2_000, "confirm_mismatch": True},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["phone_verification"]["operator_match"] is False
    assert body["phone_verification"]["carrier_name"] == "Vodafone Romania"
    assert body["content_warning"] is not None
    assert "Vodafone Romania" in body["content_warning"]
    assert mock_accounts["source"]["balance_minor"] == 98_000


async def test_topup_matches_operator_via_legal_entity_alias(client: AsyncClient, mock_accounts, twilio_configured, monkeypatch):
    """Digi apare frecvent în bazele de carrier ca „RCS & RDS" (numele legal,
    nu brandul) — vezi service.py::_OPERATOR_CARRIER_ALIASES."""
    from app import twilio_client

    async def fake_lookup_carrier(phone_e164: str):
        return twilio_client.CarrierLookupResult(carrier_name="RCS & RDS S.A.", line_type="mobile")

    monkeypatch.setattr("app.service.twilio_client.lookup_carrier", fake_lookup_carrier)

    response = await client.post(
        "/transactions/topups",
        json={"operator": "digi", "phone_number": "0722334455", "amount_minor": 2_000},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["phone_verification"]["operator_match"] is True
    assert body["content_warning"] is None


async def test_topup_blocks_non_mobile_number(client: AsyncClient, mock_accounts, twilio_configured, monkeypatch):
    from app import twilio_client

    async def fake_lookup_carrier(phone_e164: str):
        return twilio_client.CarrierLookupResult(carrier_name="Orange Romania", line_type="landline")

    monkeypatch.setattr("app.service.twilio_client.lookup_carrier", fake_lookup_carrier)

    response = await client.post(
        "/transactions/topups",
        json={"operator": "orange", "phone_number": "0722334455", "amount_minor": 2_000},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 422
    # Blocat ÎNAINTE de orice mișcare de bani.
    assert mock_accounts["source"]["balance_minor"] == 100_000


async def test_topup_falls_back_when_twilio_lookup_fails(client: AsyncClient, mock_accounts, twilio_configured, monkeypatch):
    async def fake_lookup_carrier_failing(phone_e164: str):
        return None  # vezi twilio_client.lookup_carrier — None, nu excepție, la orice eșec

    monkeypatch.setattr("app.service.twilio_client.lookup_carrier", fake_lookup_carrier_failing)

    response = await client.post(
        "/transactions/topups",
        json={"operator": "orange", "phone_number": "0722334455", "amount_minor": 2_000},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["phone_verification"] == {
        "checked": False,
        "carrier_name": None,
        "line_type": None,
        "operator_match": None,
        "unavailable_reason": "request_failed",
    }
    assert mock_accounts["source"]["balance_minor"] == 98_000
