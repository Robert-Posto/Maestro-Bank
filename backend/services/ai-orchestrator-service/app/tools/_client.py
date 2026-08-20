"""Client HTTP comun pentru toate tool-urile — vorbește STRICT cu API
Gateway-ul (NU direct cu microserviciile, NU cu MongoDB), propagând
header-ul Authorization al userului curent neschimbat. Vezi task-ul,
secțiunea 2: "Agentul trebuie să se comporte ca un client al API
Gateway-ului."
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings
from app.tools.errors import ToolError

logger = logging.getLogger("ai-orchestrator-service.tools")


async def _request(
    method: str,
    path: str,
    authorization_header: str,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
) -> Any:
    """{method} către {GATEWAY_URL}/api/{path}. `path` NU include /api —
    ex. "accounts/me", "budgets/budgets/{id}".
    """
    url = f"{settings.gateway_url}/api/{path}"
    try:
        async with httpx.AsyncClient(timeout=settings.gateway_timeout_seconds) as client:
            response = await client.request(
                method, url, headers={"Authorization": authorization_header}, params=params, json=json
            )
    except httpx.TimeoutException as exc:
        logger.warning("tool: timeout la %s %s", method, path)
        raise ToolError(f"Serviciul pentru '{path}' nu a răspuns la timp.") from exc
    except httpx.RequestError as exc:
        logger.warning("tool: eroare de rețea la %s %s", method, path)
        raise ToolError(f"Serviciul pentru '{path}' este indisponibil momentan.") from exc

    if response.status_code == 401:
        raise ToolError("Sesiunea nu mai este validă — te rugăm să te reautentifici.")
    if response.status_code == 404:
        raise ToolError(f"Nu am găsit date pentru '{path}'.")
    if response.status_code >= 400:
        logger.warning("tool: %s %s -> HTTP %s", method, path, response.status_code)
        detail = _extract_detail(response)
        raise ToolError(detail or f"Nu am putut duce la capăt cererea pentru '{path}' (eroare {response.status_code}).")

    if response.status_code == 204 or not response.content:
        return None
    return response.json()


def _extract_detail(response: httpx.Response) -> str | None:
    """Extrage `detail` dintr-un răspuns FastAPI de eroare, dacă există —
    e util în fluxul de confirmare (ex. validarea budgets-service pe
    limit_minor/name), ca mesajul văzut de user să fie cel real, nu unul generic.
    """
    try:
        body = response.json()
    except ValueError:
        return None
    detail = body.get("detail") if isinstance(body, dict) else None
    return detail if isinstance(detail, str) else None


async def gateway_get(path: str, authorization_header: str, params: dict[str, Any] | None = None) -> Any:
    return await _request("GET", path, authorization_header, params=params)


async def gateway_post(path: str, authorization_header: str, json: dict[str, Any]) -> Any:
    return await _request("POST", path, authorization_header, json=json)


async def gateway_patch(path: str, authorization_header: str, json: dict[str, Any]) -> Any:
    return await _request("PATCH", path, authorization_header, json=json)


async def gateway_delete(path: str, authorization_header: str) -> None:
    await _request("DELETE", path, authorization_header)
