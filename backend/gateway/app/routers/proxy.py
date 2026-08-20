"""Rutare (forwarding) generică către microservicii, prin API Gateway.

Regulă generală: gateway primește /api/{service}/{path...} și
redirecționează cererea către microserviciul corespunzător, folosind
adresele INTERNE din rețeaua Docker Compose (NU localhost — acelea sunt
văzute doar în interiorul rețelei, browserul nu le poate accesa).

NOTĂ despre prefixe interne: auth-service și transactions-service își
expun propriile rute sub un prefix cu numele lor (ex. intern:
/auth/register, /transactions/transfers), pe când accounts-service și
budgets-service expun rute fără prefix suplimentar (ex. intern: /me).
De aceea fiecare intrare din SERVICES are propriul `internal_prefix`,
aplicat înainte de forwarding.

JWT: rutele "sensibile" (orice ține de bani/identitate) sunt validate AICI
— în Gateway — înainte de orice forwarding, folosind `_is_protected`. Un
token lipsă/invalid primește 401 direct de la Gateway, fără ca cererea să
mai ajungă la microserviciu. Microserviciul din spate primește totuși
header-ul Authorization original (forwardat automat) și își face propria
validare independentă (defense in depth) pentru rutele lui protejate.
"""

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

from app.config import settings
from app.security import get_current_user_id

router = APIRouter()

SERVICES: dict[str, dict[str, str]] = {
    "auth": {"base_url": settings.auth_service_url, "internal_prefix": "/auth"},
    "accounts": {"base_url": settings.accounts_service_url, "internal_prefix": ""},
    "transactions": {"base_url": settings.transactions_service_url, "internal_prefix": "/transactions"},
    "budgets": {"base_url": settings.budgets_service_url, "internal_prefix": ""},
    "support": {"base_url": settings.support_service_url, "internal_prefix": ""},
    "exchange": {"base_url": settings.exchange_service_url, "internal_prefix": ""},
    "verification": {"base_url": settings.verification_service_url, "internal_prefix": ""},
}

# Headere care nu trebuie retransmise ca atare (sunt specifice conexiunii
# curente, nu au sens propagate mai departe).
_HOP_BY_HOP_REQUEST_HEADERS = {"host", "content-length"}
_HOP_BY_HOP_RESPONSE_HEADERS = {"content-length", "transfer-encoding", "connection"}


def _is_protected(service: str, path: str) -> bool:
    """Determină dacă o rută necesită JWT valid, ÎNAINTE de forwarding.

    Regulă:
      - auth: "me" și "change-password" sunt protejate (register/login
        rămân publice). La fel, sub /webauthn: register/options,
        register/verify, credentials (+ /{id}) și stepup/options sunt
        protejate — dar login/options și login/verify rămân PUBLICE
        (nu știm încă cine e userul, exact ca /auth/login cu parolă);
      - accounts: TOT e protejat (me, me/cards, cards/*, beneficiaries,
        pockets/*, dev/fund, {id});
      - transactions: TOT e protejat (nu există rute publice, inclusiv
        path="" pentru GET /api/transactions);
      - budgets: TOT e protejat (budgets, subscriptions);
      - support: TOT e protejat (tickets);
      - exchange: TOT e protejat (rate/quote personalizate per user);
      - verification: TOT e protejat (identitatea userului curent).
    """
    if service == "auth":
        if path in (
            "me",
            "change-password",
            "verify-email",
            "resend-verification-email",
            "webauthn/register/options",
            "webauthn/register/verify",
            "webauthn/credentials",
            "webauthn/stepup/options",
        ):
            return True
        return path.startswith("webauthn/credentials/")
    if service in ("accounts", "transactions", "budgets", "support", "exchange", "verification"):
        return True
    return False


async def _forward(service: str, path: str, request: Request) -> Response:
    service_config = SERVICES.get(service)
    if service_config is None:
        raise HTTPException(status_code=404, detail=f"Serviciul '{service}' nu există în gateway.")

    # Rutele /internal/* sunt DOAR pentru comunicare service-to-service
    # (auth-service -> accounts-service, transactions-service ->
    # accounts-service) — nu trebuie să fie accesibile din browser/Angular
    # prin Gateway, indiferent de serviciu.
    if path == "internal" or path.startswith("internal/"):
        raise HTTPException(status_code=404, detail="Ruta nu există.")

    if _is_protected(service, path):
        # Validare JWT ÎNAINTE de orice forwarding. Dacă lipsește/e
        # invalid, get_current_user_id ridică HTTPException(401) și
        # cererea nu mai ajunge deloc la microserviciu.
        await get_current_user_id(request.headers.get("authorization"))

    target_url = f"{service_config['base_url']}{service_config['internal_prefix']}"
    if path:
        target_url += f"/{path}"

    forwarded_headers = {
        key: value for key, value in request.headers.items() if key.lower() not in _HOP_BY_HOP_REQUEST_HEADERS
    }
    body = await request.body()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            upstream = await client.request(
                method=request.method,
                url=target_url,
                params=request.query_params,
                headers=forwarded_headers,
                content=body,
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail=f"Serviciul '{service}' nu a răspuns la timp.") from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Serviciul '{service}' este indisponibil.") from exc

    response_headers = {
        key: value for key, value in upstream.headers.items() if key.lower() not in _HOP_BY_HOP_RESPONSE_HEADERS
    }
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=upstream.headers.get("content-type"),
    )


@router.api_route("/api/{service}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_root(service: str, request: Request):
    """Cazul special al unui path fără nimic după numele serviciului
    (ex. GET /api/transactions — lista de tranzacții a userului curent)."""
    return await _forward(service, "", request)


@router.api_route("/api/{service}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy(service: str, path: str, request: Request):
    return await _forward(service, path, request)
