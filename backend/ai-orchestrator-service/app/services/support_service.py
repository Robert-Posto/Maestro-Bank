"""Orchestrare completă a unui request către Support Agent.

Leagă gate-ul de confirmare (acțiuni de scriere) cu bucla LLM
(app/agents/support.py) și tool-urile reale (app/tools/*). Singurul loc
care decide dacă un tool de scriere chiar se execută — decizia NU e
lăsată în seama modelului (vezi `_is_affirmative`, verificare determinist(ă),
testabilă independent de comportamentul GPT-5-mini).
"""

import logging

from app.agents.support import PendingConfirmationRequired, run_support_agent
from app.llm.azure_openai import AzureOpenAIClient, azure_openai_client
from app.models.support import ChatRequest, ChatResponse, PendingAction, RecommendedAction
from app.tools import support_ticket_tools

logger = logging.getLogger("ai-orchestrator-service")

# Cuvinte de confirmare acceptate (RO + EN) — verificare pe primul cuvânt
# al mesajului, ca "Da, te rog." sau "Da." să fie recunoscute, dar
# "Poate ar trebui să..." să NU fie (vezi task-ul, secțiunea 10 și 29).
_AFFIRMATIVE_WORDS = {"da", "yes", "confirm", "confirma", "confirmă", "sigur", "ok", "okay"}


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
            recommended_actions=[RecommendedAction(type="view_tickets", label="Vezi solicitările mele")],
            requires_confirmation=False,
        )
    return ChatResponse(answer="Acțiune necunoscută.", intent="unknown")  # neatins în V1


async def handle_chat(
    payload: ChatRequest,
    authorization: str,
    llm_client: AzureOpenAIClient = azure_openai_client,
) -> ChatResponse:
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

    recommended_actions = [RecommendedAction(**a) for a in recommended_actions_raw]
    return ChatResponse(
        answer=answer,
        intent=intent,
        context=context,
        recommended_actions=recommended_actions,
        requires_confirmation=False,
        metadata={"out_of_scope": True} if out_of_scope else {},
    )
