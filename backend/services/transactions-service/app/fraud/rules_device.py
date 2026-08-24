"""Familia "device" — DOAR DEV-03 în Faza 1 (restul familiei are nevoie de
loguri de sesiune/dispozitiv care nu există încă, vezi planul).

DEV-03 reintroduce singurul network hop din acest motor altfel complet
în-proces (apel către auth-service, vezi context.py::_build_device_facts).
Fail-open: dacă datele nu sunt disponibile (timeout/eroare), regula pur și
simplu nu se declanșează — vezi DeviceFacts.data_available."""

from app.fraud.models import RuleContext, RuleOutcome
from app.fraud.ruleset_config import RulesetConfig


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
