"""Logică determinist pentru propunerea creării unui Pocket (obiectiv de
economisire) — mirror EXACT pe app/services/budget_actions_service.py,
același principiu STRICT:

    GPT PROPUNE (validare + interpretare), NU EXECUTĂ.

`propose_create_pocket` de mai jos e o funcție PURĂ (fără I/O), apelată din
interiorul tool-calling-ului GPT (vezi app/tools/registry.py) — construiește
o acțiune complet specificată și validată, dar NU o trimite mai departe la
accounts-service. Rezultatul ajunge în DTO ca `pending_action`, userul vede
un buton de confirmare explicit în UI, și DOAR atunci se apelează
`execute_confirmed_action` din budget_actions_service.py (același punct de
execuție, extins cu tipul "create_pocket" — un singur loc de adevăr pentru
"GPT propune, cod determinist execută")."""

from __future__ import annotations

from app.i18n import pick
from app.services.affordability_service import format_ron
from app.tools.errors import ToolError

_NAME_MAX_LENGTH = 60  # identic cu PocketCreateRequest.name din accounts-service


def propose_create_pocket(name: str, target_minor: int) -> dict:
    normalized_name = name.strip()
    if not normalized_name:
        raise ToolError("Numele obiectivului de economisire nu poate fi gol.")
    if len(normalized_name) > _NAME_MAX_LENGTH:
        raise ToolError(f"Numele obiectivului e prea lung (max {_NAME_MAX_LENGTH} caractere).")
    if target_minor <= 0:
        raise ToolError("Ținta de economisire trebuie să fie un număr pozitiv.")

    payload = {"name": normalized_name, "target_minor": target_minor}
    target_text = format_ron(target_minor)
    summary = pick(
        f"Creez obiectivul de economisire „{normalized_name}” — țintă {target_text}.",
        f'I\'ll create the "{normalized_name}" savings goal — target {target_text}.',
    )
    return {"type": "create_pocket", "summary": summary, "payload": payload}
