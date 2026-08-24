"""Tool-uri de cont pentru Support Agent — apelează EXCLUSIV
/api/accounts/me prin Gateway (vezi app/tools/_gateway_client.py)."""

from typing import Any

from app.tools._gateway_client import GatewayError, gateway_request


async def get_my_account(authorization: str) -> dict[str, Any]:
    """Contul curent RON al userului autentificat (IBAN, sold, monedă, status)."""
    try:
        return await gateway_request("GET", "/api/accounts/me", authorization)
    except GatewayError as exc:
        return {"error": exc.detail, "status_code": exc.status_code}
