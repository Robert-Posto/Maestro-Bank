"""Tool: creare de Pocket (obiectiv de economisire) — apelează
POST /api/accounts/pockets prin Gateway (accounts-service în spate).
Vezi app/services/pocket_actions_service.py pentru validarea/propunerea
(GPT propune, NU execută) — acest modul e apelat STRICT din
execute_confirmed_action, după click pe "Confirmă".
"""

from __future__ import annotations

from app.tools._client import gateway_post


async def create_pocket(name: str, target_minor: int, authorization_header: str) -> dict:
    """Shape (din accounts-service, vezi app/models.py::PocketOut):
    {id, name, target_minor, saved_minor, created_at}."""
    return await gateway_post("accounts/pockets", authorization_header, json={"name": name, "target_minor": target_minor})
