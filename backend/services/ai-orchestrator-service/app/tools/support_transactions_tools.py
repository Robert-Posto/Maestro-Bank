"""Tool-uri de tranzacții/transferuri pentru Support Agent — apelează
EXCLUSIV /api/transactions/* prin Gateway (vezi app/tools/_gateway_client.py).
"""

from typing import Any

from app.tools._gateway_client import GatewayError, gateway_request


async def get_transaction_details(authorization: str, transaction_id: str) -> dict[str, Any]:
    """Detaliile complete ale unei tranzacții a userului, după ID."""
    try:
        return await gateway_request("GET", f"/api/transactions/{transaction_id}", authorization)
    except GatewayError as exc:
        return {"error": exc.detail, "status_code": exc.status_code}


async def get_recent_transactions(authorization: str, limit: int = 10) -> Any:
    """Cele mai recente tranzacții ale userului (implicit 10, max 50)."""
    limit = max(1, min(int(limit), 50))
    try:
        return await gateway_request("GET", "/api/transactions", authorization, params={"limit": limit})
    except GatewayError as exc:
        return {"error": exc.detail, "status_code": exc.status_code}


async def get_transfer_status(authorization: str, transaction_id: str) -> dict[str, Any]:
    """Statusul unui transfer — identic cu get_transaction_details, pentru
    că un transfer ESTE o tranzacție (nu există o entitate "transfer"
    separată în backend). Dacă status="failed", backendul NU stochează un
    motiv explicit — agentul nu trebuie să inventeze unul (vezi system prompt)."""
    return await get_transaction_details(authorization, transaction_id)
