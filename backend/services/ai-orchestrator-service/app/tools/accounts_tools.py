"""Tool: date despre contul curent al userului — apelează
GET /api/accounts/me prin Gateway (accounts-service în spate).
"""

from __future__ import annotations

from app.tools._client import gateway_get


async def get_account_balance(authorization_header: str) -> dict:
    """Soldul curent + IBAN + monedă ale contului curent al userului.

    Shape (din accounts-service, vezi app/models.py::AccountOut):
      {id, user_id, iban, currency, balance_minor, status, created_at, account_type}
    """
    return await gateway_get("accounts/me", authorization_header)
