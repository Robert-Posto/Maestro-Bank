"""DTO-uri (request/response) pentru investments-service. Formele
documentelor Mongo trăiesc informal în app/service.py (fără schema Pydantic
separată pentru documente, la fel ca restul serviciilor din acest backend)."""

from datetime import datetime

from pydantic import BaseModel, Field


class InstrumentOut(BaseModel):
    """Un rând din catalog SAU din indici + prețul lui curent (cache) —
    folosit de GET /investments/instruments și GET /investments/indices."""

    symbol: str
    name: str
    price_minor: int | None  # None dacă prețul n-a fost încă populat (primul boot)
    previous_close_minor: int | None
    change_percent: float | None  # (price - previous_close) / previous_close * 100
    updated_at: datetime | None
    category: str | None  # None pt. indici — vezi app/catalog.py::CATEGORIES


class HistoryPoint(BaseModel):
    date: str
    price_minor: int


class InstrumentDetailOut(BaseModel):
    """Vizualizarea de detalii, la click — vezi GET
    /investments/instruments/{symbol}/detail. NU e cache-uit (fetch live,
    la cerere) — vezi app/prices.py::fetch_detail."""

    symbol: str
    name: str
    is_tradable: bool  # False pt indici (^GSPC etc.) — informativi, nu se cumpără direct
    price_minor: int
    previous_close_minor: int
    change_percent: float | None
    day_high_minor: int
    day_low_minor: int
    week52_high_minor: int
    week52_low_minor: int
    volume: int | None
    history: list[HistoryPoint]


class BuyRequest(BaseModel):
    symbol: str
    amount_minor: int = Field(gt=0)


class SellRequest(BaseModel):
    symbol: str
    quantity: float = Field(gt=0)


class HoldingOut(BaseModel):
    symbol: str
    name: str
    quantity: float
    avg_cost_minor_per_share: int
    current_price_minor: int
    current_value_minor: int
    unrealized_gain_minor: int
    unrealized_gain_percent: float
