"""Orchestrarea agentului Spending + Forecast — vezi task-ul, secțiunea 4:

    GPT înțelege intenția
            ↓
    tool-uri obțin datele
            ↓
    Python calculează
            ↓
    GPT explică rezultatul

GPT (prin function/tool calling) decide ce tool-uri cheamă, în funcție de
întrebare (secțiunea 16 — nu încărcăm toate datele userului de fiecare
dată). DUPĂ ce GPT termină, completăm determinist orice date lipsă din
cache, ca DTO-ul structurat întors către UI să fie mereu complet (secțiunea
12 — cardurile din UI apar mereu, indiferent de întrebare).
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

import openai
from fastapi import HTTPException, status

from app.config import settings
from app.llm.azure_openai import AzureOpenAINotConfigured, chat_completion
from app.models.spending_forecast import (
    Analysis,
    BudgetStatus,
    ChatHistoryMessage,
    EstimatedExpenses,
    FinancialSummary,
    KnowledgeSource,
    Metadata,
    PendingAction,
    RecurringPayments,
    SpendingForecastResponse,
)
from app.prompts.spending_forecast_prompt import build_system_prompt
from app.rag.retriever import Chunk, get_retriever
from app.security import AuthContext
from app.services import affordability_service, forecast_service
from app.tools.errors import ToolError
from app.tools.registry import TOOL_SCHEMAS, ToolResultCache, ensure_core_data, execute_tool

logger = logging.getLogger("ai-orchestrator-service.agent")

_FALLBACK_ANSWER = (
    "Nu am putut genera o explicație completă acum, dar mai jos ai situația ta financiară curentă."
)

# Serviciul e stateless între cereri HTTP (nu persistă nimic — vezi
# task-ul, secțiunea 18: "NU implementa vector database/long-term memory
# în acest branch") — dar conversația rămâne coerentă pentru că
# frontend-ul retrimite istoricul recent cu fiecare mesaj (vezi
# ChatRequest.history). Limită defensivă aici, indiferent ce trimite
# clientul — evită context nemărginit (cost/latență) fără să taie
# coerența unei conversații normale (câteva schimburi de replici).
_MAX_HISTORY_MESSAGES = 12


async def _rag_context(query: str) -> tuple[str | None, list[tuple[Chunk, float]]]:
    hits = await get_retriever().retrieve(query)
    if not hits:
        return None, []
    context_text = "\n\n".join(f"[{chunk.source}]\n{chunk.text}" for chunk, _score in hits)
    message = (
        "Context intern MaestroBank, relevant pentru întrebare (folosește-l DOAR pentru "
        "explicații — NU e o sursă de date live despre user):\n\n" + context_text
    )
    return message, hits


def _default_recommendation(snapshot: dict) -> str:
    """Recomandare determinist-template pentru întrebări generale (fără o
    sumă cerută explicit) — reflectă direct numerele din forecast, nu
    parafrazarea lui GPT.
    """
    end_balance = snapshot["financial_summary"]["estimated_end_balance_minor"]
    buffer_minor = snapshot["analysis"]["recommended_buffer_minor"]
    if end_balance >= buffer_minor:
        return f"La ritmul actual de cheltuire, estimăm un sold de {affordability_service.format_ron(end_balance)} la finalul lunii — peste bufferul de siguranță recomandat."
    return f"La ritmul actual de cheltuire, estimăm un sold de {affordability_service.format_ron(end_balance)} la finalul lunii — sub bufferul de siguranță recomandat de {affordability_service.format_ron(buffer_minor)}. Poate merită să reduci cheltuielile discreționare."


async def handle_message(
    auth: AuthContext, message: str, history: list[ChatHistoryMessage] | None = None
) -> SpendingForecastResponse:
    cache = ToolResultCache()
    auth_header = auth.authorization_header

    rag_message, rag_hits = await _rag_context(message)

    # Data curentă REALĂ, determinist — GPT n-are voie s-o ghicească (vezi
    # docstring-ul din spending_forecast_prompt.py).
    current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    messages: list[dict] = [{"role": "system", "content": build_system_prompt(current_date)}]
    if rag_message:
        messages.append({"role": "system", "content": rag_message})
    # Istoricul conversației (dacă există) — vezi _MAX_HISTORY_MESSAGES mai
    # sus. Trunchiem la cele mai RECENTE mesaje, ca modelul să știe ce s-a
    # zis deja (nu mai repetă disclaimer-e, nu mai uită contextul unei
    # întrebări de follow-up).
    for entry in (history or [])[-_MAX_HISTORY_MESSAGES:]:
        messages.append({"role": entry.role, "content": entry.content})
    messages.append({"role": "user", "content": message})

    final_text: str | None = None
    try:
        for round_index in range(settings.max_tool_call_rounds):
            round_started = time.monotonic()
            logger.info("agent: rundă %s — apelez GPT (mesaje=%s)", round_index, len(messages))
            assistant_message = await chat_completion(messages, tools=TOOL_SCHEMAS)
            logger.info(
                "agent: rundă %s — GPT a răspuns în %.2fs (tool_calls=%s)",
                round_index,
                time.monotonic() - round_started,
                len(assistant_message.tool_calls or []),
            )

            if not assistant_message.tool_calls:
                final_text = assistant_message.content or ""
                break

            messages.append(
                {
                    "role": "assistant",
                    "content": assistant_message.content,
                    "tool_calls": [tool_call.model_dump() for tool_call in assistant_message.tool_calls],
                }
            )

            for tool_call in assistant_message.tool_calls:
                try:
                    arguments = json.loads(tool_call.function.arguments or "{}")
                except json.JSONDecodeError:
                    arguments = {}

                try:
                    result = await execute_tool(tool_call.function.name, arguments, auth_header, cache)
                    tool_content = json.dumps(result)
                except ToolError as exc:
                    logger.warning("agent: tool %s a eșuat: %s", tool_call.function.name, exc)
                    tool_content = json.dumps({"error": str(exc)})

                messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": tool_content})
        else:
            logger.warning(
                "agent: limita de %s runde de tool-calling a fost atinsă fără răspuns final",
                settings.max_tool_call_rounds,
            )
    except AzureOpenAINotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Asistentul AI nu este configurat momentan.",
        ) from exc
    except openai.OpenAIError as exc:
        logger.warning("agent: eroare Azure OpenAI: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Nu am putut contacta asistentul AI. Te rugăm să încerci din nou.",
        ) from exc

    if final_text is None:
        final_text = _FALLBACK_ANSWER

    # Garantăm date complete pentru DTO, indiferent ce tool-uri a ales GPT
    # să cheme pentru textul lui (vezi docstring-ul modulului).
    try:
        await ensure_core_data(cache, auth_header)
    except ToolError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    snapshot = forecast_service.build_snapshot(
        account=cache.account,
        spending_summary=cache.spending_summary,
        forecast=cache.forecast,
        subscriptions=cache.subscriptions,
        cash_flow=cache.cash_flow,
    )

    if cache.affordability is not None:
        affordable = cache.affordability["affordable"]
        requested_amount_minor = cache.affordability["requested_amount_minor"]
        snapshot["analysis"]["recommended_buffer_minor"] = cache.affordability["recommended_buffer_minor"]
        recommendation = affordability_service.render_recommendation(cache.affordability)
    else:
        affordable = None
        requested_amount_minor = None
        recommendation = _default_recommendation(snapshot)

    return SpendingForecastResponse(
        answer=final_text,
        affordable=affordable,
        requested_amount_minor=requested_amount_minor,
        analysis=Analysis(**snapshot["analysis"]),
        recurring_payments=RecurringPayments(**snapshot["recurring_payments"]),
        estimated_expenses=EstimatedExpenses(**snapshot["estimated_expenses"]),
        financial_summary=FinancialSummary(**snapshot["financial_summary"]),
        recommendation=recommendation,
        budgets=[BudgetStatus(**b) for b in cache.budget_status] if cache.budget_status is not None else None,
        pending_action=PendingAction(**cache.pending_action) if cache.pending_action is not None else None,
        metadata=Metadata(),
        knowledge_used=[
            KnowledgeSource(source=chunk.source, score=round(score, 3)) for chunk, score in rag_hits
        ],
    )
