"""Teste pentru investments-service.

Apelurile către accounts-service (_get_usd_account, _debit_account,
_credit_account) sunt MOCK-uite aici, la fel ca la deposits-service.
Cache-ul de prețuri e populat DIRECT în baza de test (nu mock-uit) — e o
colecție locală a acestui serviciu, nu un apel cross-service.

Rulare (cu stack-ul pornit prin `docker compose up`, bază de TEST separată):

    docker compose exec investments-service pip install pytest==8.3.3 pytest-asyncio==0.24.0 httpx==0.27.2 -q
    docker compose exec -e MONGO_URL=mongodb://mongodb:27017/investments_db_test investments-service python -m pytest -q
"""

from datetime import datetime, timezone

import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from app.database import get_database
from app.main import app
from app.models import BuyRequest, SellRequest

USER_ID = str(ObjectId())
USD_ACCOUNT_ID = str(ObjectId())


@pytest.fixture(autouse=True)
async def clean_collections():
    db = get_database()
    await db.holdings.delete_many({})
    await db.price_cache.delete_many({})
    yield
    await db.holdings.delete_many({})
    await db.price_cache.delete_many({})


@pytest.fixture
def mock_accounts(monkeypatch):
    state = {"balance_minor": 1_000_000}  # 10.000,00 USD disponibili

    async def fake_get_usd_account(user_id: str) -> dict:
        return {"id": USD_ACCOUNT_ID, "iban": "RO_USD", "currency": "USD", "balance_minor": state["balance_minor"], "status": "active", "account_type": "usd"}

    async def fake_debit(account_id: str, amount_minor: int) -> None:
        assert account_id == USD_ACCOUNT_ID
        if amount_minor > state["balance_minor"]:
            from fastapi import HTTPException, status
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Sold insuficient.")
        state["balance_minor"] -= amount_minor

    async def fake_credit(account_id: str, amount_minor: int) -> None:
        state["balance_minor"] += amount_minor

    monkeypatch.setattr("app.service._get_usd_account", fake_get_usd_account)
    monkeypatch.setattr("app.service._debit_account", fake_debit)
    monkeypatch.setattr("app.service._credit_account", fake_credit)
    return state


async def _seed_price(symbol: str, price_minor: int, previous_close_minor: int | None = None) -> None:
    await get_database().price_cache.update_one(
        {"_id": symbol},
        {
            "$set": {
                "name": symbol,
                "price_minor": price_minor,
                "previous_close_minor": previous_close_minor if previous_close_minor is not None else price_minor,
                "updated_at": datetime.now(timezone.utc),
                "source": "yahoo",
            }
        },
        upsert=True,
    )


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --- Cumpărare ---------------------------------------------------------------


async def test_buy_debits_account_and_creates_holding(mock_accounts):
    from app.service import buy

    await _seed_price("AAPL", 20_000)  # 200,00 USD/acțiune
    holding = await buy(USER_ID, BuyRequest(symbol="AAPL", amount_minor=100_000))  # 1.000 USD

    assert holding.quantity == pytest.approx(5.0)  # 1000 / 200
    assert holding.avg_cost_minor_per_share == 20_000
    assert mock_accounts["balance_minor"] == 900_000


async def test_buy_computes_weighted_average_on_second_purchase(mock_accounts):
    from app.service import buy

    await _seed_price("AAPL", 20_000)
    await buy(USER_ID, BuyRequest(symbol="AAPL", amount_minor=100_000))  # 5 acțiuni @ 200

    await _seed_price("AAPL", 30_000)  # prețul a crescut la 300
    holding = await buy(USER_ID, BuyRequest(symbol="AAPL", amount_minor=60_000))  # 2 acțiuni @ 300

    # medie ponderată: (200*5 + 300*2) / 7 = 1600/7 = 228.57...
    assert holding.quantity == pytest.approx(7.0)
    assert holding.avg_cost_minor_per_share == round((20_000 * 5 + 30_000 * 2) / 7)


async def test_buy_rejects_invalid_symbol(mock_accounts):
    from app.service import buy

    with pytest.raises(Exception) as exc_info:
        await buy(USER_ID, BuyRequest(symbol="NOTREAL", amount_minor=1_000))
    assert exc_info.value.status_code == 400


async def test_buy_rejects_when_price_not_cached(mock_accounts):
    from app.service import buy

    with pytest.raises(Exception) as exc_info:
        await buy(USER_ID, BuyRequest(symbol="AAPL", amount_minor=1_000))
    assert exc_info.value.status_code == 503


async def test_buy_propagates_insufficient_funds(mock_accounts):
    from app.service import buy

    await _seed_price("AAPL", 20_000)
    with pytest.raises(Exception) as exc_info:
        await buy(USER_ID, BuyRequest(symbol="AAPL", amount_minor=5_000_000))
    assert exc_info.value.status_code == 409


# --- Vânzare -------------------------------------------------------------------


async def test_sell_credits_account_and_reduces_quantity(mock_accounts):
    from app.service import buy, sell

    await _seed_price("AAPL", 20_000)
    await buy(USER_ID, BuyRequest(symbol="AAPL", amount_minor=100_000))  # 5 acțiuni
    balance_after_buy = mock_accounts["balance_minor"]

    holding = await sell(USER_ID, SellRequest(symbol="AAPL", quantity=2))
    assert holding.quantity == pytest.approx(3.0)
    assert mock_accounts["balance_minor"] == balance_after_buy + 2 * 20_000


async def test_sell_closes_position_when_selling_all(mock_accounts):
    from app.service import buy, sell

    await _seed_price("AAPL", 20_000)
    await buy(USER_ID, BuyRequest(symbol="AAPL", amount_minor=100_000))  # 5 acțiuni

    holding = await sell(USER_ID, SellRequest(symbol="AAPL", quantity=5))
    assert holding.quantity == 0

    remaining = await get_database().holdings.find_one({"user_id": USER_ID, "symbol": "AAPL"})
    assert remaining is None  # poziția a fost ștearsă, nu doar zero


async def test_sell_rejects_insufficient_quantity(mock_accounts):
    from app.service import buy, sell

    await _seed_price("AAPL", 20_000)
    await buy(USER_ID, BuyRequest(symbol="AAPL", amount_minor=100_000))  # 5 acțiuni

    with pytest.raises(Exception) as exc_info:
        await sell(USER_ID, SellRequest(symbol="AAPL", quantity=10))
    assert exc_info.value.status_code == 409


async def test_sell_rejects_no_holding(mock_accounts):
    from app.service import sell

    await _seed_price("AAPL", 20_000)
    with pytest.raises(Exception) as exc_info:
        await sell(USER_ID, SellRequest(symbol="AAPL", quantity=1))
    assert exc_info.value.status_code == 409


# --- Portofoliu ----------------------------------------------------------------


async def test_portfolio_computes_unrealized_gain(mock_accounts):
    from app.service import buy, get_portfolio

    await _seed_price("AAPL", 20_000)
    await buy(USER_ID, BuyRequest(symbol="AAPL", amount_minor=100_000))  # 5 acțiuni @ 200

    await _seed_price("AAPL", 25_000)  # prețul a crescut la 250
    portfolio = await get_portfolio(USER_ID)

    assert len(portfolio) == 1
    assert portfolio[0].current_value_minor == round(5 * 25_000)
    # cost = 5*20.000 = 100.000; valoare curentă = 5*25.000 = 125.000; câștig = 25.000
    assert portfolio[0].unrealized_gain_minor == 25_000
    assert portfolio[0].unrealized_gain_percent == pytest.approx(25.0)


async def test_list_instruments_returns_catalog_with_prices(mock_accounts):
    from app.service import list_instruments

    await _seed_price("AAPL", 20_000)
    instruments = await list_instruments()

    assert len(instruments) == 16  # tot catalogul, inclusiv simboluri fără preț cache-uit încă
    aapl = next(i for i in instruments if i.symbol == "AAPL")
    assert aapl.price_minor == 20_000
    unpriced = next(i for i in instruments if i.symbol == "MSFT")
    assert unpriced.price_minor is None


async def test_list_instruments_computes_change_percent(mock_accounts):
    from app.service import list_instruments

    await _seed_price("AAPL", 22_000, previous_close_minor=20_000)  # +10%
    instruments = await list_instruments()

    aapl = next(i for i in instruments if i.symbol == "AAPL")
    assert aapl.change_percent == pytest.approx(10.0)


async def test_list_indices_returns_indices_not_catalog(mock_accounts):
    from app.service import list_indices

    await _seed_price("^GSPC", 500_000, previous_close_minor=495_000)
    indices = await list_indices()

    assert len(indices) == 6
    symbols = {i.symbol for i in indices}
    assert "^GSPC" in symbols
    assert "AAPL" not in symbols  # indicii sunt separați de catalogul tranzacționabil
    gspc = next(i for i in indices if i.symbol == "^GSPC")
    assert gspc.change_percent == pytest.approx(round((500_000 - 495_000) / 495_000 * 100, 2))


# --- Detalii instrument (click) -------------------------------------------------


async def test_get_instrument_detail_marks_catalog_symbol_tradable(monkeypatch, mock_accounts):
    from app.service import get_instrument_detail

    async def fake_fetch_detail(symbol: str) -> dict:
        return {
            "price_minor": 20_000,
            "previous_close_minor": 19_000,
            "day_high_minor": 20_500,
            "day_low_minor": 19_800,
            "week52_high_minor": 25_000,
            "week52_low_minor": 15_000,
            "volume": 12_345_678,
            "history": [{"date": "2026-08-01", "price_minor": 19_000}, {"date": "2026-08-27", "price_minor": 20_000}],
        }

    monkeypatch.setattr("app.service.fetch_detail", fake_fetch_detail)

    detail = await get_instrument_detail("AAPL")
    assert detail.is_tradable is True
    assert detail.change_percent == pytest.approx(round((20_000 - 19_000) / 19_000 * 100, 2))
    assert len(detail.history) == 2


async def test_get_instrument_detail_marks_index_not_tradable(monkeypatch, mock_accounts):
    from app.service import get_instrument_detail

    async def fake_fetch_detail(symbol: str) -> dict:
        return {
            "price_minor": 500_000,
            "previous_close_minor": 500_000,
            "day_high_minor": 505_000,
            "day_low_minor": 495_000,
            "week52_high_minor": 520_000,
            "week52_low_minor": 400_000,
            "volume": None,
            "history": [],
        }

    monkeypatch.setattr("app.service.fetch_detail", fake_fetch_detail)

    detail = await get_instrument_detail("^GSPC")
    assert detail.is_tradable is False


async def test_get_instrument_detail_rejects_unknown_symbol(mock_accounts):
    from app.service import get_instrument_detail

    with pytest.raises(Exception) as exc_info:
        await get_instrument_detail("NOTREAL")
    assert exc_info.value.status_code == 404


# --- Endpoint HTTP ---------------------------------------------------------------


async def test_buy_endpoint_requires_auth(client: AsyncClient):
    response = await client.post("/investments/buy", json={"symbol": "AAPL", "amount_minor": 1_000})
    assert response.status_code == 401
