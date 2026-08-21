"""Tool-uri de card pentru Support Agent — apelează EXCLUSIV
/api/accounts/me/cards prin Gateway (vezi app/tools/_gateway_client.py)."""

from typing import Any

from app.tools._gateway_client import GatewayError, gateway_request


async def get_my_cards(authorization: str) -> Any:
    """Toate cardurile userului autentificat."""
    try:
        return await gateway_request("GET", "/api/accounts/me/cards", authorization)
    except GatewayError as exc:
        return {"error": exc.detail, "status_code": exc.status_code}


async def get_card_status(authorization: str, last_four: str | None = None) -> dict[str, Any]:
    """Statusul detaliat al unui card (activ/blocat, plăți online/contactless/
    internaționale, limită zilnică). Dacă `last_four` nu e dat, întoarce
    primul card al userului — majoritatea userilor demo au un singur card."""
    cards = await get_my_cards(authorization)
    if isinstance(cards, dict) and "error" in cards:
        return cards
    if not cards:
        return {"error": "Userul nu are niciun card.", "status_code": 404}
    if last_four:
        match = next((c for c in cards if c.get("last_four") == last_four), None)
        if match is None:
            return {"error": f"Nu există niciun card cu ultimele 4 cifre {last_four}.", "status_code": 404}
        return match
    return cards[0]
