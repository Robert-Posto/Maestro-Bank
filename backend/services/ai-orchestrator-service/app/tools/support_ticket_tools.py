"""Tool-uri de tichete de suport pentru Support Agent — apelează EXCLUSIV
/api/support/tickets prin Gateway (vezi app/tools/_gateway_client.py).

`create_support_ticket` este SINGURUL tool de SCRIERE al Support Agent —
NICIODATĂ apelat direct din bucla de tool-calling LLM (vezi
app/agents/support.py::WRITE_TOOLS); execuția reală se face doar după
confirmare explicită, în app/services/support_service.py.
"""

from typing import Any

from app.tools._gateway_client import GatewayError, gateway_request

TICKET_CATEGORIES = ("card", "transfer", "account", "technical", "other")


async def create_support_ticket(authorization: str, subject: str, category: str, message: str) -> dict[str, Any]:
    category = category if category in TICKET_CATEGORIES else "other"
    try:
        return await gateway_request(
            "POST",
            "/api/support/tickets",
            authorization,
            json={"subject": subject, "category": category, "message": message},
        )
    except GatewayError as exc:
        return {"error": exc.detail, "status_code": exc.status_code}


async def get_my_support_tickets(authorization: str) -> Any:
    try:
        return await gateway_request("GET", "/api/support/tickets", authorization)
    except GatewayError as exc:
        return {"error": exc.detail, "status_code": exc.status_code}
