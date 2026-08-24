"""Punctele publice de intrare apelate din app/service.py::create_transfer
— vezi hook-ul 1 (scor + audit, imediat după insert, înainte de aplicarea
efectivă a transferului) și hook-ul 2 (actualizare profil, imediat după ce
statusul devine "completed"). Restul pachetului fraud/ NU e apelat direct
de nicăieri altundeva.

GARANȚIE DE SHADOW MODE (Faza 1): `evaluate_and_record_transfer_risk`
întoarce banda de decizie DOAR când `not settings.fraud_shadow_mode` —
altfel (shadow mode, motor dezactivat, sau evaluare eșuată) întoarce
ÎNTOTDEAUNA None, indiferent ce a calculat scorul intern. Scorul e scris în
Mongo ÎN INTERIORUL acestei funcții; ce ajunge înapoi la create_transfer e
STRICT banda ("pass"/"notify"/"step_up"/"hold"), niciodată scorul brut sau
regulile declanșate — separarea "de ce" (audit, doar scris) de "ce se
întâmplă acum" (banda, singurul lucru pe care create_transfer îl poate
citi) rămâne intactă chiar și cu aplicarea reală activă.

Traversarea liniei "None mereu" din Faza 1 spre "banda reală, condiționat
de shadow mode" e DELIBERATĂ, revizuită — vezi planul fazei "PENDING
hold" — nu o eroziune accidentală a garanției inițiale.
"""

import logging
from datetime import datetime

from bson import ObjectId

from app.config import settings
from app.fraud import audit, context, scoring
from app.fraud.profile import update_profile_after_transfer
from app.fraud.ruleset_config import get_active_ruleset
from app.fraud.timeutil import to_naive_utc

logger = logging.getLogger("transactions-service")


async def evaluate_and_record_transfer_risk(
    *, transaction_id: ObjectId, transaction: dict, source_account: dict, user_id: str, evaluated_at: datetime
) -> str | None:
    if not settings.fraud_engine_enabled:
        return None

    # Tot corpul e într-un SINGUR try — inclusiv normalizarea/ruleset-ul —
    # ca garanția "nu poate niciodată crăpa transferul" să fie reală, nu
    # doar valabilă "de obicei". Wrapper-ul suplimentar din
    # app/service.py::create_transfer e apărare pe mai multe straturi,
    # pentru un bug ipotetic chiar în acest bloc except.
    try:
        normalized_at = to_naive_utc(evaluated_at)
        ruleset = get_active_ruleset()
        ctx = await context.build_rule_context(
            transaction_id=transaction_id,
            transaction=transaction,
            source_balance_minor=source_account["balance_minor"],
            user_id=user_id,
            evaluated_at=normalized_at,
            ruleset=ruleset,
        )
        result = scoring.evaluate(ctx, ruleset)
        await audit.record_evaluation(
            transaction_id=transaction_id, user_id=user_id, result=result, evaluated_at=normalized_at
        )
        if settings.fraud_shadow_mode:
            return None
        return result.decision_would_apply
    except Exception as exc:
        logger.error(
            "fraud: evaluare eșuată (tx_id=%s, user_id=%s) — se scrie o înregistrare degradată: %s",
            transaction_id,
            user_id,
            exc,
        )
        try:
            await audit.record_evaluation_error(
                transaction_id=transaction_id,
                user_id=user_id,
                ruleset_version=get_active_ruleset().version,
                evaluated_at=to_naive_utc(evaluated_at),
                error=exc,
            )
        except Exception:
            logger.critical(
                "fraud: scrierea înregistrării de eroare a EȘUAT și ea (tx_id=%s, user_id=%s) — "
                "vezi audit.py pentru fallback-ul de logging complet al înregistrării",
                transaction_id,
                user_id,
            )
        return None  # explicit — o evaluare eșuată NU are voie să gateze transferul


async def record_completed_transfer_for_profile(*, user_id: str, transaction: dict, evaluated_at: datetime) -> None:
    """Best-effort — vezi profile.py::update_profile_after_transfer. NU e
    artefactul de conformitate (acela e hook-ul 1 de mai sus); un profil
    stale/lipsă doar degradează spre cold start la următoarea evaluare."""
    if not settings.fraud_engine_enabled:
        return
    try:
        await update_profile_after_transfer(
            user_id=user_id,
            amount_minor=transaction["amount_minor"],
            category=transaction["category"],
            to_iban=transaction["to_iban"],
            created_at=to_naive_utc(evaluated_at),
        )
    except Exception as exc:
        logger.warning("fraud: actualizare profil eșuată (user_id=%s): %s", user_id, exc)
