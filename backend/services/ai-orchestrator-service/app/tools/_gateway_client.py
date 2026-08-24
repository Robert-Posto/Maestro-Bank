"""Client HTTP comun pentru toate tool-urile Support Agent.

SINGURUL loc prin care agentul vorbește cu restul sistemului. Apelează
EXCLUSIV API Gateway-ul (niciodată un microserviciu direct, niciodată o
bază de date) — vezi regula arhitecturală: Support Agent se comportă ca
orice alt client al Gateway-ului.

Header-ul Authorization e retransmis NESCHIMBAT, exact cum ar face
Angular — Gateway-ul + microserviciile din spate fac toată validarea și
izolarea per-user; acest client nu decide nimic pe baza identității și nu
acceptă niciodată un user_id trimis explicit.
"""

from typing import Any

import httpx

from app.config import settings


class GatewayError(Exception):
    """Ridicată când Gateway-ul/un microserviciu răspunde cu eroare.
    Tool-ul care o prinde o transformă într-un rezultat clar pentru LLM
    (ex. {"error": ..., "status_code": ...}), NU inventează date."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Gateway a răspuns {status_code}: {detail}")


async def gateway_request(method: str, path: str, authorization: str, **kwargs: Any) -> Any:
    url = f"{settings.gateway_url}{path}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.request(method, url, headers={"Authorization": authorization}, **kwargs)
    except httpx.RequestError as exc:
        raise GatewayError(502, f"Gateway indisponibil: {exc}") from exc

    if response.status_code == 401:
        raise GatewayError(401, "Neautorizat.")
    if response.status_code == 404:
        raise GatewayError(404, "Resursa nu a fost găsită.")
    if response.status_code >= 400:
        raise GatewayError(response.status_code, response.text)
    if response.status_code == 204 or not response.content:
        return {}
    return response.json()
