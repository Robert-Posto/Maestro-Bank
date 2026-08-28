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
from datetime import datetime, timezone
from typing import Any, Protocol

from app.config import settings
from app.i18n import translate
from app.llm.azure_openai import chat_completion
from app.models.support import ChatMessage
from app.prompts.support_prompt import build_support_system_prompt
from app.services import safety_guard
from app.tools import (
    support_accounts_tools,
    support_cards_tools,
    support_exchange_tools,
    support_ticket_tools,
    support_transactions_tools,
)

logger = logging.getLogger("ai-orchestrator-service")

# Serviciul e stateless între cereri HTTP — frontend-ul retrimite istoricul
# la fiecare mesaj (acum persistat în sessionStorage, vezi
# features/support/support.ts, deci poate crește mult în timp). Limită
# defensivă aici, indiferent ce trimite clientul (vezi și
# app/models/support.py::ChatRequest.history, max_length=40) — evită
# context nemărginit (cost/latență), fără să taie coerența unei conversații
# normale. Identic ca valoare cu Spending + Forecast Agent (vezi
# app/agents/spending_forecast.py::_MAX_HISTORY_MESSAGES).
_MAX_HISTORY_MESSAGES = 12


class SupportLLMClient(Protocol):
    """Interfața minimă de care are nevoie bucla de mai jos — implementată
    atât de `_ChatCompletionAdapter` (producție, mai jos), cât și de
    `FakeLLMClient` din teste (vezi tests/conftest.py), ca cele două să
    poată fi interschimbate fără nicio altă modificare în acest fișier."""

    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Any: ...


class _ChatCompletionAdapter:
    """Adaptor subțire peste `app.llm.azure_openai.chat_completion` (clientul
    Azure OpenAI comun, folosit deja de Spending + Forecast Agent — vezi
    app/agents/spending_forecast.py), ca Support Agent să NU mai aibă
    propriul client Azure separat. Singurul motiv de a exista: Support
    Agent a fost scris inițial cu o interfață bazată pe clase (`.complete()`,
    vezi tests/conftest.py::FakeLLMClient) — păstrăm exact acea interfață
    aici, ca testele existente să rămână neschimbate.
    """

    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Any:
        return await chat_completion(messages, tools=tools)


_default_llm_client = _ChatCompletionAdapter()

_READ_TOOL_MODULES: dict[str, Any] = {
    "get_my_account": support_accounts_tools,
    "get_my_accounts": support_accounts_tools,
    "get_my_cards": support_cards_tools,
    "get_card_status": support_cards_tools,
    "get_transaction_details": support_transactions_tools,
    "get_recent_transactions": support_transactions_tools,
    "get_transactions_by_period": support_transactions_tools,
    "get_transactions_by_date_range": support_transactions_tools,
    "get_transfer_status": support_transactions_tools,
    "get_my_support_tickets": support_ticket_tools,
    "get_exchange_rates": support_exchange_tools,
    "get_exchange_quote": support_exchange_tools,
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
    "get_transactions_by_period": "transactions",
    "get_transactions_by_date_range": "transactions",
    "get_transaction_details": "transaction",
    "get_transfer_status": "transaction",
    "get_card_status": "card",
    "get_my_cards": "cards",
    "get_my_account": "account",
    "get_my_accounts": "accounts",
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
            "name": "get_my_accounts",
            "description": (
                "Întoarce TOATE conturile reale ale userului autentificat (curent + economii/depozit/"
                "student, dacă are), fiecare cu `account_type`. Folosește ACEST tool (nu get_my_account) "
                "pentru orice întrebare despre ce conturi are userul deja — ex. 'am cont de economii?', "
                "'ce conturi am', 'am deschis un depozit?'."
            ),
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
            "name": "get_transactions_by_period",
            "description": (
                "Întoarce tranzacțiile userului dintr-o perioadă NUMITĂ, cu limite EXACTE calculate "
                "determinist (NU de tine). Folosește ACEST tool, NU get_recent_transactions, de îndată "
                "ce userul menționează (explicit sau implicit) un interval de timp — 'luna trecută', "
                "'luna asta', 'săptămâna asta', 'azi', 'ultimele 7/30/90 de zile'. NU încerca să deduci "
                "singur ce e 'luna trecută' dintr-o listă brută de tranzacții — vei greși."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": ["today", "this_week", "this_month", "last_month", "last_7_days", "last_30_days", "last_90_days"],
                    },
                    "limit": {"type": "integer", "description": "Câte tranzacții maxim, implicit 50."},
                },
                "required": ["period"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_transactions_by_date_range",
            "description": (
                "Întoarce tranzacțiile userului într-un interval EXPLICIT, cerut de user cu date concrete "
                "(ex. 'de pe 15 august până pe 20', 'între 1 și 10 iulie'). Folosește ACEST tool, NU "
                "get_transactions_by_period, când userul dă date concrete care nu se potrivesc cu o "
                "perioadă numită (today/this_week/this_month/last_month/last_N_days). Dacă userul nu "
                "specifică anul, folosește anul din directiva 'Data curentă' a promptului de sistem — "
                "NU ghici, NU folosi anul din memoria ta de antrenare."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {"type": "string", "description": "Data de început, format YYYY-MM-DD."},
                    "date_to": {"type": "string", "description": "Data de sfârșit (inclusiv), format YYYY-MM-DD."},
                    "limit": {"type": "integer", "description": "Câte tranzacții maxim, implicit 100."},
                },
                "required": ["date_from", "date_to"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_exchange_rates",
            "description": (
                "Întoarce cursurile curente (BNR + comisionul MaestroBank) pentru toate valutele "
                "suportate. Folosește-l pentru o întrebare generală despre curs, FĂRĂ o sumă anume "
                "de convertit (ex. 'cât e cursul la euro azi?')."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_exchange_quote",
            "description": (
                "Calculează o cotație REALĂ (curs BNR + comisionul MaestroBank, exact ca pagina "
                "Schimb valutar) pentru schimbul unei sume dintr-o valută în alta. Folosește ACEST "
                "tool pentru orice întrebare de tip 'cât ar fi X RON în EUR' / 'cât primesc dacă "
                "schimb 50 de euro' — NU ghici, NU calcula tu un curs, NU refuza răspunsul cu "
                "'nu am informația asta' (schimbul valutar AI o sursă certă, spre deosebire de alte "
                "comisioane despre care chiar nu ai date)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "from_currency": {"type": "string", "description": "Cod ISO 3 litere, ex. RON."},
                    "to_currency": {"type": "string", "description": "Cod ISO 3 litere, ex. EUR."},
                    "amount": {
                        "type": "number",
                        "description": "Suma în unități întregi ale valutei sursă (ex. 100 pentru 100 RON), NU în bani/cenți.",
                    },
                },
                "required": ["from_currency", "to_currency", "amount"],
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
                        "description": (
                            "Sugestii de follow-up, afișate ca butoane clickable. `type` TREBUIE să fie din "
                            "enum-ul de mai jos — NU inventa alte valori. Cele care încep cu 'navigate_' duc "
                            "userul REAL la acea pagină din aplicație (ruta e rezolvată determinist de backend, "
                            "nu de tine); 'view_tickets' și 'ask_followup' retrimit `label` ca mesaj nou către tine."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": [
                                        "navigate_cards",
                                        "navigate_accounts",
                                        "navigate_transactions",
                                        "navigate_transfers",
                                        "navigate_exchange",
                                        "navigate_budgets",
                                        "navigate_spending_forecast",
                                        "navigate_profile",
                                        "open_support_ticket",
                                        "view_tickets",
                                        "ask_followup",
                                    ],
                                },
                                "label": {"type": "string", "maxLength": 60},
                            },
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
    llm_client: SupportLLMClient = _default_llm_client,
) -> tuple[str, str, list[dict[str, Any]], bool, dict[str, Any]]:
    """Rulează bucla de tool-calling GPT-5-mini pentru Support Agent.

    Întoarce (answer, intent, recommended_actions, out_of_scope, context).
    `context` conține rezultatele BRUTE ale tool-urilor "prezentabile"
    apelate în acest tur (vezi `_CONTEXT_KEY_BY_TOOL`) — frontend-ul le
    poate randa cu UI real (listă de tranzacții cu avatar comerciant etc.),
    fără să depindă de cum a parafrazat modelul datele în `answer`.

    Ridică `PendingConfirmationRequired` dacă modelul cere un tool de scriere.
    """
    # Date sensibile de card (PIN/CVV/număr complet) sau încercări de a
    # scoate promptul de sistem -> NU trecem deloc prin GPT (vezi
    # app/services/safety_guard.py) — răspuns determinist, la fel ca la
    # limbajul jignitor din Spending + Forecast Agent (vezi
    # spending_forecast.py::handle_message — Support Agent nu avea încă
    # niciun filtru determinist ÎNAINTE de acest task).
    if safety_guard.detect_sensitive_data(message):
        logger.info("Support Agent: mesaj cu date sensibile de card — răspuns determinist, fără apel GPT")
        return translate("sensitiveDataWarning"), "unknown", [], False, {}
    if safety_guard.detect_prompt_extraction_attempt(message):
        logger.info("Support Agent: încercare de extragere a promptului — răspuns determinist, fără apel GPT")
        return translate("promptExtractionRefusal"), "unknown", [], False, {}

    current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    messages: list[dict[str, Any]] = [{"role": "system", "content": build_support_system_prompt(current_date)}]
    messages.extend({"role": m.role, "content": m.content} for m in history[-_MAX_HISTORY_MESSAGES:])
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
                # NU mai verificăm ieșirea GPT-ului cu safety_guard (vezi
                # docstring-ul modulului acela pentru motiv — un fals-pozitiv
                # real, confirmat live: mențiunea normală "PIN" din
                # contextul plăților, combinată cu orice cod scurt din
                # același răspuns (ex. last_four), transforma un răspuns
                # corect de status card într-un avertisment confuz).
                # Mesajul userului tot e verificat, ÎNAINTE de buclă (vezi
                # detect_sensitive_data mai sus) — acolo e riscul real.
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
        translate("supportFallbackAnswer"),
        "unknown",
        [],
        False,
        collected_context,
    )
