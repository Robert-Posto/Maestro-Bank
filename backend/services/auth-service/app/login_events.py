"""Urmărirea încercărilor de autentificare (auth_db.login_events) —
separată de service.py, la fel ca webauthn_service.py, pentru că
alimentează un consumator conceptual diferit (motorul de fraudă din
transactions-service), nu fluxul de autentificare în sine.

O înregistrare per ÎNCERCARE de login, succes SAU eșec — VEL-04 (fraud)
are nevoie explicit de eșecuri, nu doar de sesiuni reușite. Geolocalizarea
(app/geoip.py) rulează DOAR pe succese (o încercare eșuată nu spune nimic
despre "unde e userul", doar despre "cineva a încercat" — și înjumătățește
apelurile către API-ul extern)."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone

from app.database import get_database
from app.geoip import lookup_ip

logger = logging.getLogger("auth-service")

_RECENT_EVENTS_LIMIT = 200
_RECENT_EVENTS_MAX_AGE_DAYS = 90


def compute_device_signature(ip_address: str | None, user_agent: str | None) -> str | None:
    """Proxy pentru un fingerprint real de dispozitiv — un fingerprint
    ADEVĂRAT ar necesita cod JS client-side (canvas/screen/fonturi etc.),
    disproporționat pentru acest demo. Doar un hash scurt IP+User-Agent,
    documentat explicit ca aproximare, NU o identificare reală de
    dispozitiv (vezi planul fazei)."""
    if not ip_address and not user_agent:
        return None
    raw = f"{ip_address or ''}|{user_agent or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def extract_client_ip(request) -> str | None:
    """`X-Real-IP` (setat de nginx) -> primul hop din `X-Forwarded-For`
    (setat tot de nginx, redundant, dar mai robust dacă cineva schimbă
    proxy-ul) -> IP-ul direct al conexiunii (fallback dev, ex. apel direct
    către auth-service, fără nginx în față). Header-ele CHIAR ajung azi la
    auth-service, neschimbate — vezi planul fazei, nimeni nu le citea
    încă."""
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else None


async def record_login_attempt(
    *, user_id: str | None, email_attempted: str, success: bool, ip_address: str | None, user_agent: str | None
) -> None:
    device_signature = compute_device_signature(ip_address, user_agent)
    geo = await lookup_ip(ip_address) if (success and ip_address) else None

    doc = {
        "user_id": user_id,
        "email_attempted": email_attempted,
        "success": success,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "device_signature": device_signature,
        "country": geo.country if geo else None,
        "lat": geo.lat if geo else None,
        "lon": geo.lon if geo else None,
        "created_at": datetime.now(timezone.utc),
    }
    db = get_database()
    try:
        await db.login_events.insert_one(doc)
    except Exception as exc:
        # NICIODATĂ nu lăsăm o scriere de audit eșuată să blocheze login-ul
        # — la fel ca fraud/audit.py din transactions-service.
        logger.error("auth-service: scriere login_events EȘUATĂ (user_id=%s): %s", user_id, exc)


async def get_recent_login_events(user_id: str) -> list[dict]:
    """Istoricul recent (succese ȘI eșecuri) al userului — consumat DOAR
    de /internal/security-facts (transactions-service, motorul de fraudă).
    Toate comparațiile relative la momentul evaluării (ex. "ultimele 24h")
    sunt responsabilitatea APELANTULUI — la fel ca DEV-03, acest modul
    întoarce fapte brute, nu decizii."""
    db = get_database()
    cutoff = datetime.now(timezone.utc) - timedelta(days=_RECENT_EVENTS_MAX_AGE_DAYS)
    return (
        await db.login_events.find({"user_id": user_id, "created_at": {"$gte": cutoff}})
        .sort("created_at", -1)
        .to_list(length=_RECENT_EVENTS_LIMIT)
    )


async def ensure_login_event_indexes() -> None:
    db = get_database()
    await db.login_events.create_index([("user_id", 1), ("created_at", -1)])
