"""Tool-uri de cont pentru Support Agent — apelează EXCLUSIV
/api/accounts/me și /api/accounts/all prin Gateway (vezi
app/tools/_gateway_client.py)."""

from typing import Any

from app.tools._gateway_client import GatewayError, gateway_request


async def get_my_account(authorization: str) -> dict[str, Any]:
    """Contul curent RON al userului autentificat (IBAN, sold, monedă, status)."""
    try:
        return await gateway_request("GET", "/api/accounts/me", authorization)
    except GatewayError as exc:
        return {"error": exc.detail, "status_code": exc.status_code}


async def get_my_accounts(authorization: str) -> Any:
    """TOATE conturile userului autentificat (curent + economii/depozit/
    student, dacă are) — folosește pentru "ce conturi am"/"am cont de
    economii?", NU doar contul curent (vezi get_my_account, mai sus). Fiecare
    element are `account_type` — sursă REALĂ pentru ce conturi are userul
    deja, spre deosebire de ce tipuri POATE deschide (informație statică,
    vezi system prompt)."""
    try:
        return await gateway_request("GET", "/api/accounts/all", authorization)
    except GatewayError as exc:
        return {"error": exc.detail, "status_code": exc.status_code}
