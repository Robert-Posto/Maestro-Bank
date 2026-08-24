"""Orchestrarea Guardian — DOAR acest modul are voie să scrie
`guardian.*` (fraud_evaluations) și `risk.phrase`/`risk.status`
(transactions). Vezi app/service.py::create_transfer pentru cele două
puncte de intrare: `compute_customer_risk` (pur, sincron, apelat direct
în request) și `generate_guardian_explanations` (async, apelat DOAR din
BackgroundTasks)."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId

from app.config import settings
from app.database import get_database
from app.guardian import llm_client, prompt, templates

logger = logging.getLogger("transactions-service")

# Benzile pentru care se generează o FRAZĂ pentru client (via LLM, cu
# fallback pe șablon) — "safe" și "held" au deja fraze FIXE, sincrone, fără
# LLM (vezi compute_customer_risk). Fixată de propriul tău spec, NU
# configurabilă — spre deosebire de guardian_staff_report_bands.
_CUSTOMER_PHRASE_BANDS = {"notify", "step_up"}

_RULE_ID_PATTERN = re.compile(r"\b[A-Z]{3}-\d{2}\b")
_CUSTOMER_PHRASE_MAX_LEN = 300
_STAFF_EXPLANATION_MAX_LEN = 800


def compute_customer_risk(informational_band: str | None, is_held: bool) -> dict[str, Any]:
    """PURĂ, sincronă — apelată direct din create_transfer, NU dintr-un
    background task. `informational_band` e decision_would_apply, valoarea
    NECONDIȚIONATĂ (scrisă mereu de audit.py, indiferent de shadow mode) —
    NU banda întoarsă de evaluate_and_record_transfer_risk (aceea rămâne
    None sub shadow mode, prin garanția ei proprie, nemodificată aici).

    `is_held` reconciliază banda teoretică cu ce s-a întâmplat REALMENTE:
    o bandă "hold" cu shadow mode activ NU a reținut nimic cu adevărat, deci
    clientul nu are voie să vadă "HELD" — cade pe "potentially_dangerous"."""
    if informational_band == "notify":
        return {"tier": "unusual", "phrase": None, "status": "pending"}
    if informational_band == "step_up":
        return {"tier": "potentially_dangerous", "phrase": None, "status": "pending"}
    if informational_band == "hold":
        if is_held:
            return {"tier": "held", "phrase": templates.HELD_CUSTOMER_PHRASE, "status": "ready"}
        return {"tier": "potentially_dangerous", "phrase": None, "status": "pending"}
    # None / "pass" / orice valoare neașteptată — implicit sigur.
    return {"tier": "safe", "phrase": templates.SAFE_CUSTOMER_PHRASE, "status": "ready"}


def _validate_customer_phrase(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    # Chiar dacă prompt-ul interzice explicit ID-uri de regulă, mai
    # verificăm o dată aici — centură ȘI bretele, niciodată doar politică.
    if not cleaned or _RULE_ID_PATTERN.search(cleaned):
        return None
    return cleaned[:_CUSTOMER_PHRASE_MAX_LEN]


def _validate_staff_explanation(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned[:_STAFF_EXPLANATION_MAX_LEN]


async def generate_guardian_explanations(*, transaction_id: ObjectId, user_id: str) -> None:
    """Apelată DOAR din BackgroundTasks (vezi app/service.py::create_transfer).
    Singurele scrieri permise: `guardian` (fraud_evaluations) și
    `risk.phrase`/`risk.status` (transactions, DOAR când risk.status era
    deja "pending" — un hold real, cu fraza fixă deja setată sincron, NU e
    atins aici). Cheile `$set` sunt LITERALE, fixe — output-ul LLM-ului e
    citit STRICT prin `.get("customer_phrase")`/`.get("staff_explanation")`,
    niciodată desfăcut (`**parsed`) într-un update — vezi planul fazei,
    secțiunea "Security enforcement"."""
    if not settings.guardian_enabled:
        return

    db = get_database()
    evaluation = await db.fraud_evaluations.find_one({"transaction_id": transaction_id})
    if evaluation is None:
        logger.warning("guardian: nicio evaluare fraud găsită pentru tx_id=%s — nimic de explicat", transaction_id)
        return

    score = evaluation.get("score")
    band = evaluation.get("decision_would_apply")
    fired_rules = evaluation.get("fired_rules") or []
    fired_rule_ids = [rule["rule_id"] for rule in fired_rules]

    messages = prompt.build_messages(evaluation)
    parsed = await llm_client.complete_json(messages)

    customer_phrase = _validate_customer_phrase(parsed.get("customer_phrase") if parsed else None)
    customer_from_llm = customer_phrase is not None
    if customer_phrase is None:
        customer_phrase = templates.build_template_customer_phrase(fired_rule_ids)

    staff_explanation = _validate_staff_explanation(parsed.get("staff_explanation") if parsed else None)
    staff_from_llm = staff_explanation is not None
    if staff_explanation is None:
        staff_explanation = templates.build_template_staff_explanation(score, band, fired_rules)

    overall_source = "llm" if (customer_from_llm and staff_from_llm) else "template"

    transaction = await db.transactions.find_one({"_id": transaction_id}, {"risk": 1})
    risk = (transaction or {}).get("risk") or {}

    guardian_doc = {
        "status": "ready" if overall_source == "llm" else "template_fallback",
        "staff_explanation": staff_explanation,
        "customer_tier": risk.get("tier"),
        "customer_phrase": customer_phrase,
        "source": overall_source,
        "generated_at": datetime.now(timezone.utc),
        "model": settings.azure_openai_deployment if overall_source == "llm" else None,
    }
    await db.fraud_evaluations.update_one({"transaction_id": transaction_id}, {"$set": {"guardian": guardian_doc}})

    # DOAR benzile lăsate "pending" sincron (notify/step_up, sau hold cu
    # shadow mode) primesc fraza aici — un hold REAL a fost deja finalizat
    # sincron cu HELD_CUSTOMER_PHRASE, "safe" la fel cu SAFE_CUSTOMER_PHRASE.
    if risk.get("status") == "pending":
        await db.transactions.update_one(
            {"_id": transaction_id},
            {
                "$set": {
                    "risk.phrase": customer_phrase,
                    "risk.status": "ready" if customer_from_llm else "template_fallback",
                }
            },
        )
