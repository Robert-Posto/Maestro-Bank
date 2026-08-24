"""Support Agent — bucla de tool-calling peste GPT-5-mini (Azure OpenAI).

Separare READ vs WRITE (vezi task-ul MaestroBank, secțiunea 17):
  - READ_TOOLS sunt executate imediat, ori de câte ori modelul le cere.
  - WRITE_TOOLS NU sunt NICIODATĂ executate aici — dacă modelul cere un
    astfel de tool, bucla se oprește imediat și ridică
    `PendingConfirmationRequired`, prinsă de app/services/support_service.py,
    care implementează gate-ul de confirmare explicită.

Tool-urile sunt rezolvate prin `getattr(modul, nume)` LA MOMENTUL
APELULUI (nu prin referințe directe stocate într-un dict la import) —
astfel testele pot monkeypatch-ui funcțiile din app/tools/* exact ca-n
restul proiectului (vezi tests/conftest.py).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import settings
from app.llm.azure_openai import AzureOpenAIClient, azure_openai_client
from app.models.support import ChatMessage
from app.prompts.support_prompt import SUPPORT_SYSTEM_PROMPT
from app.tools import support_accounts_tools, support_cards_tools, support_ticket_tools, support_transactions_tools

logger = logging.getLogger("ai-orchestrator-service")

_READ_TOOL_MODULES: dict[str, Any] = {
    "get_my_account": support_accounts_tools,
    "get_my_cards": support_cards_tools,
    "get_card_status": support_cards_tools,
    "get_transaction_details": support_transactions_tools,
    "get_recent_transactions": support_transactions_tools,
    "get_transfer_status": support_transactions_tools,
    "get_my_support_tickets": support_ticket_tools,
}

WRITE_TOOLS = {"create_support_ticket"}

CONTROL_TOOL = "respond_to_user"

# Rezultatul BRUT (neatins de LLM) al unor tool-uri "prezentabile" e pus
# în `context`-ul răspunsului final, sub cheia de mai jos — frontend-ul îl
# randează cu componente UI reale (avatar comerciant, bule colorate pe
# categorie etc.), NU doar ca text. Populat determinist, de orchestrator,
# NU de model — modelul nu poate "inventa" sau denatura ce ajunge aici.
_CONTEXT_KEY_BY_TOOL: dict[str, str] = {
    "get_recent_transactions": "transactions",
    "get_transaction_details": "transaction",
    "get_transfer_status": "transaction",
    "get_card_status": "card",
    "get_my_cards": "cards",
    "get_my_account": "account",
    "get_my_support_tickets": "tickets",
}

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_my_account",
            "description": "Întoarce contul curent RON al userului autentificat (IBAN, sold, status).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_cards",
            "description": "Întoarce toate cardurile userului autentificat.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_card_status",
            "description": (
                "Întoarce statusul detaliat al unui card (activ/blocat, plăți online/contactless/"
                "internaționale, limită zilnică). Dacă userul nu specifică un card anume, NU trimite "
                "last_four — se întoarce automat primul card al userului."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "last_four": {"type": "string", "description": "Ultimele 4 cifre ale cardului, opțional."}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_transaction_details",
            "description": "Întoarce detaliile complete ale unei tranzacții a userului, după ID.",
            "parameters": {
                "type": "object",
                "properties": {"transaction_id": {"type": "string"}},
                "required": ["transaction_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_transactions",
            "description": "Întoarce cele mai recente tranzacții ale userului (implicit 10, max 50).",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "description": "Câte tranzacții, implicit 10."}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_transfer_status",
            "description": "Întoarce statusul unui transfer (o tranzacție de tip transfer), după ID.",
            "parameters": {
                "type": "object",
                "properties": {"transaction_id": {"type": "string"}},
                "required": ["transaction_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_support_tickets",
            "description": "Întoarce toate tichetele de suport ale userului autentificat.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_support_ticket",
            "description": (
                "Creează un tichet de suport nou pentru userul autentificat. IMPORTANT: nu apela "
                "acest tool decât DUPĂ ce userul a confirmat explicit, într-un mesaj anterior, că "
                "vrea să creezi tichetul — dacă nu a confirmat încă, întreabă-l mai întâi în text, "
                "prin respond_to_user, fără să apelezi acest tool."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "maxLength": 140},
                    "category": {
                        "type": "string",
                        "enum": ["card", "transfer", "account", "technical", "other"],
                    },
                    "message": {"type": "string", "maxLength": 4000},
                },
                "required": ["subject", "category", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": CONTROL_TOOL,
            "description": "Încheie conversația cu un răspuns final, structurat, către user. OBLIGATORIU la final.",
            "parameters": {
                "type": "object",
                "properties": {
                    "answer": {"type": "string"},
                    "intent": {
                        "type": "string",
                        "enum": [
                            "account_help",
                            "card_status",
                            "card_help",
                            "transaction_details",
                            "transaction_not_recognized",
                            "transfer_status",
                            "navigation_help",
                            "support_ticket",
                            "unknown",
                        ],
                    },
                    "recommended_actions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"type": {"type": "string"}, "label": {"type": "string"}},
                            "required": ["type", "label"],
                        },
                    },
                    "out_of_scope": {"type": "boolean"},
                },
                "required": ["answer", "intent"],
            },
        },
    },
]


class PendingConfirmationRequired(Exception):
    """Ridicată când modelul cere un tool de SCRIERE — bucla se oprește
    aici, fără să execute nimic. Prinsă de app/services/support_service.py."""

    def __init__(self, tool: str, arguments: dict[str, Any]) -> None:
        self.tool = tool
        self.arguments = arguments
        super().__init__(f"Tool '{tool}' necesită confirmare explicită înainte de execuție.")


async def run_support_agent(
    message: str,
    history: list[ChatMessage],
    authorization: str,
    llm_client: AzureOpenAIClient = azure_openai_client,
) -> tuple[str, str, list[dict[str, Any]], bool, dict[str, Any]]:
    """Rulează bucla de tool-calling GPT-5-mini pentru Support Agent.

    Întoarce (answer, intent, recommended_actions, out_of_scope, context).
    `context` conține rezultatele BRUTE ale tool-urilor "prezentabile"
    apelate în acest tur (vezi `_CONTEXT_KEY_BY_TOOL`) — frontend-ul le
    poate randa cu UI real (listă de tranzacții cu avatar comerciant etc.),
    fără să depindă de cum a parafrazat modelul datele în `answer`.

    Ridică `PendingConfirmationRequired` dacă modelul cere un tool de scriere.
    """
    messages: list[dict[str, Any]] = [{"role": "system", "content": SUPPORT_SYSTEM_PROMPT}]
    messages.extend({"role": m.role, "content": m.content} for m in history)
    messages.append({"role": "user", "content": message})

    collected_context: dict[str, Any] = {}

    for _ in range(settings.agent_max_tool_iterations):
        response_message = await llm_client.complete(messages, TOOL_SCHEMAS)
        tool_calls = getattr(response_message, "tool_calls", None)

        if not tool_calls:
            # Fallback — modelul ar trebui să folosească mereu respond_to_user,
            # dar nu ne bazăm strict pe asta pentru un răspuns utilizabil.
            return response_message.content or "", "unknown", [], False, collected_context

        messages.append(
            {
                "role": "assistant",
                "content": response_message.content,
                "tool_calls": [tc.model_dump() for tc in tool_calls],
            }
        )

        for tool_call in tool_calls:
            name = tool_call.function.name
            try:
                arguments: dict[str, Any] = json.loads(tool_call.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}

            if name == CONTROL_TOOL:
                return (
                    arguments.get("answer", ""),
                    arguments.get("intent", "unknown"),
                    arguments.get("recommended_actions", []),
                    bool(arguments.get("out_of_scope", False)),
                    collected_context,
                )

            if name in WRITE_TOOLS:
                raise PendingConfirmationRequired(tool=name, arguments=arguments)

            module = _READ_TOOL_MODULES.get(name)
            tool_fn = getattr(module, name, None) if module is not None else None
            if tool_fn is None:
                result: Any = {"error": f"Tool necunoscut: {name}"}
            else:
                result = await tool_fn(authorization, **arguments)

            context_key = _CONTEXT_KEY_BY_TOOL.get(name)
            if context_key and not (isinstance(result, dict) and "error" in result):
                collected_context[context_key] = result

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, default=str),
                }
            )

    logger.warning("Support Agent: prea multe iterații fără respond_to_user — fallback.")
    return (
        "Nu am putut finaliza răspunsul — poți reformula întrebarea, te rog?",
        "unknown",
        [],
        False,
        collected_context,
    )
