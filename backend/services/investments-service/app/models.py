"""DTO-uri (request/response) pentru investments-service. Formele
documentelor Mongo trăiesc informal în app/service.py (fără schema Pydantic
separată pentru documente, la fel ca restul serviciilor din acest backend)."""

from datetime import datetime

from pydantic import BaseModel, Field


class InstrumentOut(BaseModel):
    """Un rând din catalog + prețul lui curent (cache) — folosit de
    GET /investments/instruments, pentru ca frontend-ul să afișeze
    catalogul înainte ca userul să aleagă ce cumpără."""

    symbol: str
    name: str
    price_minor: int | None  # None dacă prețul n-a fost încă populat (primul boot)
    updated_at: datetime | None


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
