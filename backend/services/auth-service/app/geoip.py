"""Geolocalizare IP — DOAR pentru semnale de fraudă (DEV-04/DEV-05,
consumate de transactions-service), apelată STRICT la login (nu pe calea
de plată — transactions-service doar citește evenimentele deja stocate,
vezi app/login_events.py). Folosește ip-api.com (gratuit, fără cheie),
timeout scurt + fail-open, la fel ca orice alt semnal opțional din acest
motor — o geolocalizare eșuată/indisponibilă NU blochează NICIODATĂ
login-ul, doar lasă `country`/`lat`/`lon` necompletate pe acel eveniment.

IP-urile private/loopback/rezervate sunt SĂRITE fără niciun apel extern —
ar întoarce oricum "reserved range" de la orice serviciu real, și în acest
demo ele sunt MAJORITATEA traficului (rețea Docker/LAN internă, nu
internet public) — a le sări conservă și limita de 45 cereri/minut a
nivelului gratuit ip-api.com."""

from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger("auth-service")

_TIMEOUT_SECONDS = 2.0
_GEOIP_URL_TEMPLATE = "http://ip-api.com/json/{ip}"  # nivelul gratuit e doar HTTP, nu HTTPS


@dataclass(frozen=True)
class GeoResult:
    country: str | None
    lat: float | None
    lon: float | None


def _is_lookupable(ip_address: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_address)
    except ValueError:
        return False
    return not (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast)


async def lookup_ip(ip_address: str) -> GeoResult | None:
    """None = fără informație de locație (IP privat/nelocalizabil, sau
    apelul a eșuat/expirat) — apelantul (login_events.py) o tratează
    identic în ambele cazuri, nu distinge motivul."""
    if not _is_lookupable(ip_address):
        return None
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.get(
                _GEOIP_URL_TEMPLATE.format(ip=ip_address), params={"fields": "status,countryCode,lat,lon"}
            )
        body = response.json()
        if body.get("status") != "success":
            return None
        return GeoResult(country=body.get("countryCode"), lat=body.get("lat"), lon=body.get("lon"))
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("auth-service: geolocalizare IP eșuată pentru %s: %s", ip_address, exc)
        return None
