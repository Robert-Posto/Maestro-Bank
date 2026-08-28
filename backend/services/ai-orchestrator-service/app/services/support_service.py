"""Orchestrare completă a unui request către Support Agent.

Leagă gate-ul de confirmare (acțiuni de scriere) cu bucla LLM
(app/agents/support.py) și tool-urile reale (app/tools/*). Singurul loc
care decide dacă un tool de scriere chiar se execută — decizia NU e
lăsată în seama modelului (vezi `_is_affirmative`, verificare determinist(ă),
testabilă independent de comportamentul GPT-5-mini).
"""

import logging

from app.agents.support import PendingConfirmationRequired, SupportLLMClient, _default_llm_client, run_support_agent
from app.models.support import ChatRequest, ChatResponse, PendingAction, RecommendedAction
from app.services import moderation_service
from app.tools import support_ticket_tools

logger = logging.getLogger("ai-orchestrator-service")

# Cuvinte de confirmare acceptate (RO + EN) — verificare pe primul cuvânt
# al mesajului, ca "Da, te rog." sau "Da." să fie recunoscute, dar
# "Poate ar trebui să..." să NU fie (vezi task-ul, secțiunea 10 și 29).
_AFFIRMATIVE_WORDS = {"da", "yes", "confirm", "confirma", "confirmă", "sigur", "ok", "okay"}

# Rute REALE Angular (vezi frontend/src/app/app.routes.ts) — singura sursă
# de adevăr pentru unde duce un `recommended_action` de tip "navigate_*".
# GPT alege DOAR `type` (constrâns la enum-ul din TOOL_SCHEMAS, vezi
# app/agents/support.py) — NU inventează niciodată o rută; ruta reală e
# rezolvată STRICT aici, determinist. Un `type` care nu apare aici (ex.
# "view_tickets", "ask_followup") înseamnă "fără navigare" — frontend-ul
# retrimite `label` ca mesaj nou, în loc să navigheze.
_ACTION_ROUTES: dict[str, str] = {
    "navigate_cards": "/app/cards",
    "navigate_accounts": "/app/accounts",
    "navigate_transactions": "/app/transactions",
    "navigate_transfers": "/app/transfers",
    "navigate_exchange": "/app/exchange",
    "navigate_investments": "/app/investments",
    "navigate_points": "/app/points",
    "navigate_loans": "/app/loans",
    "navigate_budgets": "/app/budgets",
    "navigate_spending_forecast": "/app/spending-forecast",
    "navigate_profile": "/app/profile",
    # Deschide DIRECT modalul de tichet nou (vezi Support::ngOnInit, care
    # citește query param-ul "newTicket") — nu doar pagina de suport goală.
    "open_support_ticket": "/app/support?newTicket=1",
}


def _build_recommended_action(type_: str, label: str) -> RecommendedAction:
    return RecommendedAction(type=type_, label=label, route=_ACTION_ROUTES.get(type_))


def _is_affirmative(text: str) -> bool:
    normalized = text.strip().lower().rstrip(".!")
    if not normalized:
        return False
    first_word = normalized.split()[0].strip(",")
    return first_word in _AFFIRMATIVE_WORDS


def _build_confirmation_question(tool: str, arguments: dict) -> str:
    if tool == "create_support_ticket":
        subject = arguments.get("subject", "")
        category = arguments.get("category", "other")
        return (
            f'Vrei să creez o solicitare de suport cu subiectul "{subject}" '
            f'(categorie: {category})? Confirmă cu "da".'
        )
    return "Confirmi această acțiune?"


async def _execute_confirmed_action(pending: PendingAction, authorization: str) -> ChatResponse:
    if pending.tool == "create_support_ticket":
        result = await support_ticket_tools.create_support_ticket(authorization, **pending.arguments)
        if isinstance(result, dict) and "error" in result:
            return ChatResponse(
                answer=f"Nu am putut crea solicitarea: {result['error']}",
                intent="support_ticket",
                context=result,
                requires_confirmation=False,
            )
        return ChatResponse(
            answer=f"Solicitarea a fost creată cu numărul {result.get('id')}. Status: {result.get('status', 'open')}.",
            intent="support_ticket",
            context={"ticket": result},
            recommended_actions=[_build_recommended_action("view_tickets", "Vezi solicitările mele")],
            requires_confirmation=False,
        )
    return ChatResponse(answer="Acțiune necunoscută.", intent="unknown")  # neatins în V1


async def handle_chat(
    payload: ChatRequest,
    authorization: str,
    llm_client: SupportLLMClient = _default_llm_client,
) -> ChatResponse:
    # Limbaj jignitor/injurii -> NU trecem deloc prin GPT (același filtru
    # determinist ca la Spending + Forecast Agent — vezi
    # app/services/moderation_service.py și app/agents/spending_forecast.py
    # pentru precedent) — răspuns determinist, cerem reformularea, fără să
    # irosim niciun apel real și fără să abandonăm un `pending_action` din
    # turul anterior pe baza unui mesaj pe care oricum nu-l „răspundem".
    if moderation_service.contains_profanity(payload.message):
        logger.info("support_service: mesaj cu limbaj jignitor — răspuns determinist, fără apel GPT")
        return ChatResponse(answer=moderation_service.REPHRASE_REQUEST_ANSWER, intent="unknown")

    if payload.pending_action is not None:
        if _is_affirmative(payload.message):
            return await _execute_confirmed_action(payload.pending_action, authorization)
        # Userul NU a confirmat explicit — abandonăm acțiunea propusă și
        # tratăm mesajul curent ca o întrebare nouă, normală (fall-through).

    try:
        answer, intent, recommended_actions_raw, out_of_scope, context = await run_support_agent(
            message=payload.message,
            history=payload.history,
            authorization=authorization,
            llm_client=llm_client,
        )
    except PendingConfirmationRequired as exc:
        return ChatResponse(
            answer=_build_confirmation_question(exc.tool, exc.arguments),
            intent="support_ticket",
            requires_confirmation=True,
            metadata={"pending_action": {"tool": exc.tool, "arguments": exc.arguments}},
        )

    recommended_actions = [
        _build_recommended_action(a.get("type", ""), a.get("label", "")) for a in recommended_actions_raw
    ]
    return ChatResponse(
        answer=answer,
        intent=intent,
        context=context,
        recommended_actions=recommended_actions,
        requires_confirmation=False,
        metadata={"out_of_scope": True} if out_of_scope else {},
    )
