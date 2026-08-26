"""Familia "device" (DEV-01, DEV-02, DEV-03, DEV-04, DEV-05, DEV-06) —
pure, vezi rules_amount.py pentru convenția generală.

DEV-03 e cel mai vechi (Faza 1) — singurul network hop pe atunci era
apelul webauthn-latest (vezi context.py::_build_device_facts). Restul
familiei (DEV-01/02/04/05/06) folosește un AL DOILEA hop, separat
(context.py::_build_security_facts, ctx.security) — vezi planul fazei
pentru de ce sunt două apeluri distincte, nu unul singur. Ambele fail-open
identic: dacă datele nu sunt disponibile (timeout/eroare), regulile
dependente pur și simplu nu se declanșează.

Aproximare documentată, valabilă pentru TOATE regulile de mai jos în afară
de DEV-03: o cerere de transfer nu poartă niciun IP/dispozitiv propriu (doar
un JWT emis la un login anterior) — "sesiunea curentă" e aproximată drept
CEA MAI RECENTĂ autentificare REUȘITĂ a userului la momentul evaluării, nu
un identificator de sesiune real urmărit prin JWT (asta ar fi atins stratul
de autentificare al FIECĂRUI serviciu, nu doar auth-service +
transactions-service — vezi planul fazei)."""

import math
from datetime import timedelta

from app.fraud.models import RuleContext, RuleOutcome
from app.fraud.ruleset_config import RulesetConfig
from app.fraud.rules_amount import check_amt_01

_EARTH_RADIUS_KM = 6371.0


def check_dev_03(ctx: RuleContext, ruleset: RulesetConfig) -> RuleOutcome | None:
    """Passkey nou înrolat în ultimele 60 min."""
    if not ctx.device.data_available or ctx.device.latest_passkey_created_at is None:
        return None
    age_minutes = (ctx.evaluated_at - ctx.device.latest_passkey_created_at).total_seconds() / 60
    if age_minutes < 0 or age_minutes > ruleset.dev03_window_minutes:
        return None
    return RuleOutcome(
        rule_id="DEV-03",
        family="device",
        weight=ruleset.dev03_weight,
        contributes_to_score=True,
        values={"passkey_enrolled_minutes_ago": round(age_minutes, 1)},
    )


def check_dev_01(ctx: RuleContext, ruleset: RulesetConfig) -> RuleOutcome | None:
    """Semnătura de dispozitiv (aproximare hash IP+User-Agent, vezi
    context.py) a celei mai recente autentificări REUȘITE nu apare în
    NICIUNA din autentificările reușite anterioare ale acestui user.

    Subsumată de DEV-06 (vezi catalogue.py::SUBSUMED_BY) — check_dev_06 mai
    jos reutilizează CHIAR această funcție ca ingredient, deci declanșarea
    DEV-06 face acest semnal complet redundant."""
    if not ctx.security.data_available:
        return None
    successes = [event for event in ctx.security.recent_logins if event.success]
    if len(successes) < 2:
        return None  # niciun istoric anterior de comparat

    current = successes[0]
    if current.device_signature is None:
        return None

    earlier_signatures = {event.device_signature for event in successes[1:] if event.device_signature}
    if not earlier_signatures or current.device_signature in earlier_signatures:
        return None

    return RuleOutcome(
        rule_id="DEV-01",
        family="device",
        weight=ruleset.dev01_weight,
        contributes_to_score=True,
        values={"device_signature": current.device_signature},
    )


def check_dev_02(ctx: RuleContext, ruleset: RulesetConfig) -> RuleOutcome | None:
    """Parola SAU o credențială (passkey înrolat/revocat) schimbată în
    ultimele N ore — pas clasic de account takeover."""
    if not ctx.security.data_available:
        return None
    cutoff = ctx.evaluated_at - timedelta(hours=ruleset.dev02_window_hours)

    triggers: list[str] = []
    if ctx.security.password_changed_at is not None and ctx.security.password_changed_at >= cutoff:
        triggers.append("password")
    triggers.extend(
        event.event for event in ctx.security.recent_credential_events if event.created_at >= cutoff
    )

    if not triggers:
        return None
    return RuleOutcome(
        rule_id="DEV-02",
        family="device",
        weight=ruleset.dev02_weight,
        contributes_to_score=True,
        values={"triggers": triggers, "window_hours": ruleset.dev02_window_hours},
    )


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def check_dev_04(ctx: RuleContext, ruleset: RulesetConfig) -> RuleOutcome | None:
    """"Călătorie imposibilă": distanța dintre cele mai recente DOUĂ
    autentificări reușite, împărțită la timpul scurs, depășește o viteză
    plauzibilă (implicit 900 km/h). Are nevoie de coordonate — doar
    autentificările cu geolocalizare reușită (vezi geoip.py) contează."""
    if not ctx.security.data_available:
        return None
    successes = [
        event for event in ctx.security.recent_logins if event.success and event.lat is not None and event.lon is not None
    ]
    if len(successes) < 2:
        return None

    current, previous = successes[0], successes[1]
    hours_elapsed = (current.created_at - previous.created_at).total_seconds() / 3600
    if hours_elapsed <= 0:
        return None

    distance_km = _haversine_km(previous.lat, previous.lon, current.lat, current.lon)
    speed_kmh = distance_km / hours_elapsed
    if speed_kmh <= ruleset.dev04_max_plausible_kmh:
        return None

    return RuleOutcome(
        rule_id="DEV-04",
        family="device",
        weight=ruleset.dev04_weight,
        contributes_to_score=True,
        values={
            "distance_km": round(distance_km, 1),
            "hours_elapsed": round(hours_elapsed, 2),
            "speed_kmh": round(speed_kmh, 1),
        },
    )


def check_dev_05(ctx: RuleContext, ruleset: RulesetConfig) -> RuleOutcome | None:
    """Țara celei mai recente autentificări reușite absentă din TOATE
    autentificările reușite ale userului, din ultimele N zile."""
    if not ctx.security.data_available:
        return None
    successes = [event for event in ctx.security.recent_logins if event.success]
    if len(successes) < 2:
        return None

    current = successes[0]
    if current.country is None:
        return None

    cutoff = ctx.evaluated_at - timedelta(days=ruleset.dev05_window_days)
    known_countries = {event.country for event in successes[1:] if event.country and event.created_at >= cutoff}
    if not known_countries or current.country in known_countries:
        return None

    return RuleOutcome(
        rule_id="DEV-05",
        family="device",
        weight=ruleset.dev05_weight,
        contributes_to_score=True,
        values={"country": current.country, "known_countries": sorted(known_countries)},
    )


def check_dev_06(ctx: RuleContext, ruleset: RulesetConfig) -> RuleOutcome | None:
    """Combo — dispozitiv nou (DEV-01) + beneficiar nou (BEN-01) + sumă
    peste percentila personală/cohortă (AMT-01) — cel mai puternic semnal
    din catalog pentru "cineva a intrat în cont și îl golește". Reutilizează
    check_dev_01/check_amt_01 direct (ambele pure) — nu duplică logica lor."""
    if check_dev_01(ctx, ruleset) is None:
        return None
    if ctx.window.beneficiary.seen_before:
        return None
    if check_amt_01(ctx, ruleset) is None:
        return None

    return RuleOutcome(
        rule_id="DEV-06",
        family="device",
        weight=ruleset.dev06_weight,
        contributes_to_score=True,
        values={"new_device": True, "new_beneficiary": True, "amount_above_p95": True},
    )
