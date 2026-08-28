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
cache, ca DTO-ul structurat întors către UI să fie mereu complet — dar
cardurile arătate userului NU mai sunt toate mereu (vezi `_relevant_cards`
mai jos): datele sunt mereu calculate corect, afișarea lor e condiționată
de ce a chemat GPT efectiv pentru întrebarea asta (feedback: cardurile nu
trebuie să apară dacă nu au legătură cu ce s-a întrebat).
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

import openai
from fastapi import HTTPException, status

from app.config import settings
from app.i18n import pick, translate
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
from app.services import affordability_service, forecast_service, moderation_service, safety_guard
from app.tools.errors import ToolError
from app.tools.registry import TOOL_SCHEMAS, ToolResultCache, ensure_core_data, execute_tool

logger = logging.getLogger("ai-orchestrator-service.agent")

# Serviciul e stateless între cereri HTTP (nu persistă nimic — vezi
# task-ul, secțiunea 18: "NU implementa vector database/long-term memory
# în acest branch") — dar conversația rămâne coerentă pentru că
# frontend-ul retrimite istoricul recent cu fiecare mesaj (vezi
# ChatRequest.history). Limită defensivă aici, indiferent ce trimite
# clientul — evită context nemărginit (cost/latență) fără să taie
# coerența unei conversații normale (câteva schimburi de replici).
_MAX_HISTORY_MESSAGES = 12

# Cardurile din UI (Analiză / Plăți recurente rămase / Cheltuieli estimate /
# Rezumat financiar) NU mai apar mereu — doar cele relevante pentru
# întrebarea userului (feedback: "as vrea sa mi afiseze asta doar cand e
# cazul nu mereu"). DTO-ul rămâne complet (vezi ensure_core_data, mai jos —
# păstrăm secțiunea 12 din task DOAR ca "datele sunt mereu calculate",
# nu ca "sunt mereu arătate"), dar `relevant_cards` spune frontend-ului pe
# care să le afișeze, dedus din tool-urile pe care GPT a ALES să le cheme
# pentru ACEASTĂ întrebare — NU din completarea determinist-forțată de
# ensure_core_data (care rulează DUPĂ ce citim called_tools, tocmai ca să
# nu "polueze" relevanța cu date completate doar pentru integritatea DTO-ului).
_CARD_TRIGGERS: dict[str, set[str]] = {
    "get_account_balance": {"financial_summary"},
    "get_spending_summary": {"estimated_expenses"},
    "get_forecast": {"financial_summary", "estimated_expenses"},
    "get_upcoming_subscriptions": {"recurring_payments"},
    "evaluate_affordability": {"analysis"},
}
_CARD_ORDER = ["analysis", "recurring_payments", "estimated_expenses", "financial_summary"]


def _relevant_cards(called_tools: list[str]) -> list[str]:
    cards: set[str] = set()
    for tool_name in called_tools:
        cards |= _CARD_TRIGGERS.get(tool_name, set())
    return [card for card in _CARD_ORDER if card in cards]


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


def _default_recommendation(snapshot: dict, spending_summary: dict) -> str:
    """Recomandare determinist-template pentru întrebări generale (fără o
    sumă cerută explicit) — reflectă direct numerele din forecast, nu
    parafrazarea lui GPT. Include un sfat de economisire CONCRET (categoria
    discreționară cu cea mai mare cheltuială reală) atunci când există date
    pentru asta — nu un sfat generic, desprins de cont (vezi feedback
    userului: "sa ma ajute sa economisesc, sa mi dea sfaturi").
    """
    end_balance = snapshot["financial_summary"]["estimated_end_balance_minor"]
    buffer_minor = snapshot["analysis"]["recommended_buffer_minor"]
    top_category = forecast_service.top_discretionary_category(spending_summary)
    end_balance_ron = affordability_service.format_ron(end_balance)

    if end_balance >= buffer_minor:
        base = pick(
            f"La ritmul actual de cheltuire, estimăm un sold de {end_balance_ron} la finalul lunii — peste bufferul de siguranță recomandat.",
            f"At your current spending pace, we estimate a balance of {end_balance_ron} at month-end — above the recommended safety buffer.",
        )
        if top_category:
            label, amount_minor = top_category
            amount_ron = affordability_service.format_ron(amount_minor)
            base += pick(
                f" Cea mai mare cheltuială discreționară de până acum e pe {label} ({amount_ron}) — dacă vrei să economisești mai mult, e primul loc de unde ai putea reduce.",
                f" Your largest discretionary spend so far is on {label} ({amount_ron}) — if you want to save more, that's the first place to cut.",
            )
        return base

    buffer_ron = affordability_service.format_ron(buffer_minor)
    base = pick(
        f"La ritmul actual de cheltuire, estimăm un sold de {end_balance_ron} la finalul lunii — sub bufferul de siguranță recomandat de {buffer_ron}.",
        f"At your current spending pace, we estimate a balance of {end_balance_ron} at month-end — below the recommended safety buffer of {buffer_ron}.",
    )
    if top_category:
        label, amount_minor = top_category
        amount_ron = affordability_service.format_ron(amount_minor)
        base += pick(
            f" Cea mai mare cheltuială discreționară e pe {label} ({amount_ron}) — reducerea ei e cea mai rapidă cale să te apropii de buffer.",
            f" Your largest discretionary spend is on {label} ({amount_ron}) — trimming it is the fastest way to get back to the buffer.",
        )
    else:
        base += pick(
            " Merită să urmărești cheltuielile discreționare din restul lunii.",
            " It's worth keeping an eye on your discretionary spending for the rest of the month.",
        )
    return base


async def handle_message(
    auth: AuthContext, message: str, history: list[ChatHistoryMessage] | None = None
) -> SpendingForecastResponse:
    cache = ToolResultCache()
    auth_header = auth.authorization_header

    # Limbaj jignitor/injurii, date sensibile de card (PIN/CVV/număr complet)
    # sau încercări de a scoate promptul de sistem -> NU trecem deloc prin
    # GPT (vezi moderation_service.py / safety_guard.py) — răspuns
    # determinist. Verificare făcută ÎNAINTE de RAG/tool-calling, ca să nu
    # irosim niciun apel real (feedback: "la injurii vreau sa nu raspunda,
    # sa roage sa reformulezez" / "nu ma lasa sa ii dau date personale").
    if moderation_service.contains_profanity(message):
        logger.info("agent: mesaj cu limbaj jignitor — răspuns determinist, fără apel GPT")
        final_text = translate("rephraseRequest")
        relevant_cards: list[str] = []
        rag_hits: list[tuple[Chunk, float]] = []
    elif safety_guard.detect_sensitive_data(message):
        logger.info("agent: mesaj cu date sensibile de card — răspuns determinist, fără apel GPT")
        final_text = translate("sensitiveDataWarning")
        relevant_cards = []
        rag_hits = []
    elif safety_guard.detect_prompt_extraction_attempt(message):
        logger.info("agent: încercare de extragere a promptului — răspuns determinist, fără apel GPT")
        final_text = translate("promptExtractionRefusal")
        relevant_cards = []
        rag_hits = []
    else:
        rag_message, rag_hits = await _rag_context(message)

        # Data curentă REALĂ, determinist — GPT n-are voie s-o ghicească
        # (vezi docstring-ul din spending_forecast_prompt.py).
        current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        messages: list[dict] = [{"role": "system", "content": build_system_prompt(current_date)}]
        if rag_message:
            messages.append({"role": "system", "content": rag_message})
        # Istoricul conversației (dacă există) — vezi _MAX_HISTORY_MESSAGES
        # mai sus. Trunchiem la cele mai RECENTE mesaje, ca modelul să știe
        # ce s-a zis deja (nu mai repetă disclaimer-e, nu mai uită
        # contextul unei întrebări de follow-up).
        for entry in (history or [])[-_MAX_HISTORY_MESSAGES:]:
            messages.append({"role": entry.role, "content": entry.content})
        messages.append({"role": "user", "content": message})

        final_text = None
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
                detail=translate("assistantNotConfigured"),
            ) from exc
        except openai.OpenAIError as exc:
            logger.warning("agent: eroare Azure OpenAI: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=translate("assistantUnreachable"),
            ) from exc

        if final_text is None:
            final_text = translate("forecastFallbackAnswer")
        # Apărare suplimentară — vezi safety_guard.py::redact_if_sensitive.
        # Nu ar trebui să se întâmple niciodată (niciun tool nu-i oferă
        # PIN/CVV/PAN), dar costă puțin să verificăm și ce a GENERAT GPT,
        # nu doar mesajul userului (verificat mai sus, înainte de apel).
        final_text = safety_guard.redact_if_sensitive(final_text)

        # Citim called_tools ÎNAINTE de ensure_core_data — vezi
        # _CARD_TRIGGERS mai sus, relevanța cardurilor reflectă DOAR
        # alegerile reale ale GPT.
        relevant_cards = _relevant_cards(cache.called_tools)

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
        recommendation = _default_recommendation(snapshot, cache.spending_summary)

    return SpendingForecastResponse(
        answer=final_text,
        affordable=affordable,
        requested_amount_minor=requested_amount_minor,
        analysis=Analysis(**snapshot["analysis"]),
        recurring_payments=RecurringPayments(**snapshot["recurring_payments"]),
        estimated_expenses=EstimatedExpenses(**snapshot["estimated_expenses"]),
        financial_summary=FinancialSummary(**snapshot["financial_summary"]),
        recommendation=recommendation,
        relevant_cards=relevant_cards,
        budgets=[BudgetStatus(**b) for b in cache.budget_status] if cache.budget_status is not None else None,
        pending_action=PendingAction(**cache.pending_action) if cache.pending_action is not None else None,
        metadata=Metadata(),
        knowledge_used=[
            KnowledgeSource(source=chunk.source, score=round(score, 3)) for chunk, score in rag_hits
        ],
    )
