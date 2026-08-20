"""Definițiile tool-urilor (function calling) expuse modelului GPT-5-mini
+ dispatch-ul care le execută. 9 tool-uri — peste cele 5-8 orientative din
task-ul inițial, dar scope-ul a fost extins EXPLICIT (buget: citire +
propuneri de acțiuni, cu confirmare separată — vezi
app/services/budget_actions_service.py) — fiecare tool e distinct și
necesar, nu redundant.

`propose_create_budget` / `propose_update_budget` / `propose_delete_budget`
NU execută nimic — doar validează și construiesc o acțiune propusă
(`cache.pending_action`), afișată userului cu buton de confirmare
explicit. Execuția reală se întâmplă DOAR după acel click, printr-un apel
separat, fără GPT (vezi app/routers/spending_forecast.py::confirm_action).

`ToolResultCache` ține minte rezultatele DEJA obținute în timpul rundei de
tool-calling (un cont/spending/forecast/subscriptions se cer o singură
dată, chiar dacă modelul le-ar "cere" de mai multe ori sau chiar dacă mai
multe tool-uri au nevoie de aceleași date — ex. `evaluate_affordability`
are nevoie de forecast + spending). După ce bucla de tool-calling se
termină, app/agents/spending_forecast.py completează în cache orice date
lipsă (pentru DTO-ul complet, vezi secțiunea 12 — UI-ul arată toate
cardurile mereu), fără să repete apeluri deja făcute.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from app.services import affordability_service, budget_actions_service, budget_service
from app.tools import accounts_tools, budgets_tools, transactions_tools
from app.tools.errors import ToolError

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_account_balance",
            "description": "Soldul curent, IBAN și moneda contului curent al userului autentificat.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_spending_summary",
            "description": (
                "Cheltuielile userului în luna curentă: total cheltuit, ritm mediu zilnic de "
                "cheltuire, defalcare pe categorii (inclusiv care e categoria cu cea mai mare cheltuială)."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_forecast",
            "description": (
                "Forecast determinist al soldului estimat la finalul lunii curente, plus "
                "obligațiile viitoare cunoscute (abonamente cu scadență în restul lunii) și "
                "numărul de zile rămase din lună."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_upcoming_subscriptions",
            "description": "Toate abonamentele/plățile recurente active ale userului, cu ziua din lună la care se taxează.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "evaluate_affordability",
            "description": (
                "Calculează determinist dacă userul își permite o sumă cerută — compară soldul "
                "estimat de final de lună (după cheltuială) cu bufferul de siguranță recomandat. "
                "Folosește ACEST tool pentru orice întrebare de tip 'îmi permit X?'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "requested_amount_ron": {
                        "type": "number",
                        "description": "Suma cerută, în LEI (RON) — ex. 2000 pentru '2000 lei'. Trimite numărul din lei direct, NU face tu conversia în bani.",
                    }
                },
                "required": ["requested_amount_ron"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_budget_status",
            "description": (
                "Toate bugetele active ale userului, cu suma deja cheltuită luna asta pe fiecare "
                "categorie, cât mai rămâne de cheltuit și dacă bugetul a fost depășit. Folosește "
                "ACEST tool pentru 'ce bugete am', 'cât mai pot cheltui pe X', 'am depășit vreun buget'."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_create_budget",
            "description": (
                "PROPUNE crearea unui buget lunar nou — NU îl creează efectiv, userul trebuie să "
                "confirme explicit din interfață. Folosește asta când userul cere să-i faci/creezi "
                "un buget nou (ex. 'fă-mi un buget de 800 lei pentru restaurante')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": (
                            "Categoria bugetului — una din: groceries, shopping, transport, bills, "
                            "restaurants, entertainment, subscriptions, other."
                        ),
                    },
                    "limit_ron": {
                        "type": "number",
                        "description": "Limita lunară, în LEI (RON) — ex. 800 pentru '800 lei'. NU converti tu în bani.",
                    },
                    "name": {
                        "type": "string",
                        "description": "Nume opțional al bugetului — dacă lipsește, se folosește numele categoriei.",
                    },
                },
                "required": ["category", "limit_ron"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_update_budget",
            "description": (
                "PROPUNE modificarea limitei unui buget existent — NU îl modifică efectiv, userul "
                "trebuie să confirme explicit din interfață. Folosește asta când userul cere să "
                "mărească/micșoreze/schimbe un buget deja existent."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "Numele sau categoria bugetului de modificat, exact cum apare la get_budget_status.",
                    },
                    "new_limit_ron": {
                        "type": "number",
                        "description": "Noua limită lunară, în LEI (RON) — ex. 1500 pentru '1500 lei'. NU converti tu în bani.",
                    },
                },
                "required": ["target", "new_limit_ron"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_delete_budget",
            "description": (
                "PROPUNE ștergerea unui buget existent — NU îl șterge efectiv, userul trebuie să "
                "confirme explicit din interfață. Folosește asta când userul cere să șteargă/elimine un buget."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "Numele sau categoria bugetului de șters, exact cum apare la get_budget_status.",
                    }
                },
                "required": ["target"],
            },
        },
    },
]


@dataclass
class ToolResultCache:
    account: dict | None = None
    spending_summary: dict | None = None
    forecast: dict | None = None
    subscriptions: list[dict] | None = None
    cash_flow: dict | None = None
    budgets: list[dict] | None = None
    affordability: dict | None = None
    budget_status: list[dict] | None = None
    pending_action: dict | None = None
    called_tools: list[str] = field(default_factory=list)


async def _cached_account(cache: ToolResultCache, auth_header: str) -> dict:
    if cache.account is None:
        cache.account = await accounts_tools.get_account_balance(auth_header)
    return cache.account


async def _cached_spending(cache: ToolResultCache, auth_header: str) -> dict:
    if cache.spending_summary is None:
        cache.spending_summary = await transactions_tools.get_spending_summary(auth_header)
    return cache.spending_summary


async def _cached_forecast(cache: ToolResultCache, auth_header: str) -> dict:
    if cache.forecast is None:
        cache.forecast = await transactions_tools.get_forecast(auth_header)
    return cache.forecast


async def _cached_subscriptions(cache: ToolResultCache, auth_header: str) -> list[dict]:
    if cache.subscriptions is None:
        cache.subscriptions = await budgets_tools.get_upcoming_subscriptions(auth_header)
    return cache.subscriptions


async def _cached_cash_flow(cache: ToolResultCache, auth_header: str) -> dict:
    if cache.cash_flow is None:
        cache.cash_flow = await transactions_tools.get_recent_cash_flow(auth_header)
    return cache.cash_flow


async def _cached_budgets(cache: ToolResultCache, auth_header: str) -> list[dict]:
    if cache.budgets is None:
        cache.budgets = await budgets_tools.get_budgets(auth_header)
    return cache.budgets


async def ensure_core_data(cache: ToolResultCache, auth_header: str) -> None:
    """Garantează că account/spending/forecast/subscriptions/cash-flow sunt
    în cache — apelat DUPĂ bucla de tool-calling, ca DTO-ul structurat să
    fie mereu complet, indiferent ce tool-uri a ales GPT să cheme pentru
    răspunsul lui în text liber (vezi app/agents/spending_forecast.py).
    Nu repetă apeluri deja făcute în timpul rundei de tool-calling.
    """
    await asyncio.gather(
        _cached_account(cache, auth_header),
        _cached_spending(cache, auth_header),
        _cached_forecast(cache, auth_header),
        _cached_subscriptions(cache, auth_header),
        _cached_cash_flow(cache, auth_header),
    )


def _to_minor(value: object, field_name: str) -> int:
    """Convertește o sumă în LEI (unități majore, așa cum o trimite GPT —
    vezi TOOL_SCHEMAS) în bani/subunități — SINGURUL loc unde se face
    conversia ×100. GPT NU mai trebuie să facă el aritmetica asta (risc
    real de eroare de conversie, ex. de 100x) — doar extrage numărul din
    text, restul e determinist aici.
    """
    try:
        ron = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ToolError(f"„{field_name}” trebuie să fie un număr (suma în lei).") from exc
    return round(ron * 100)


async def execute_tool(name: str, arguments: dict, auth_header: str, cache: ToolResultCache) -> dict:
    cache.called_tools.append(name)
    try:
        if name == "get_account_balance":
            return await _cached_account(cache, auth_header)
        if name == "get_spending_summary":
            return await _cached_spending(cache, auth_header)
        if name == "get_forecast":
            return await _cached_forecast(cache, auth_header)
        if name == "get_upcoming_subscriptions":
            return {"subscriptions": await _cached_subscriptions(cache, auth_header)}
        if name == "evaluate_affordability":
            if "requested_amount_ron" not in arguments:
                raise ToolError("Lipsește suma cerută (requested_amount_ron).")
            requested_amount_minor = _to_minor(arguments["requested_amount_ron"], "requested_amount_ron")
            forecast = await _cached_forecast(cache, auth_header)
            spending = await _cached_spending(cache, auth_header)
            result = affordability_service.evaluate_affordability(
                requested_amount_minor=requested_amount_minor,
                estimated_end_of_month_balance_minor=forecast["estimated_end_of_month_balance_minor"],
                spending_summary=spending,
            )
            cache.affordability = result
            return result
        if name == "get_budget_status":
            budgets = await _cached_budgets(cache, auth_header)
            spending = await _cached_spending(cache, auth_header)
            status = budget_service.compute_budget_status(budgets, spending)
            cache.budget_status = status
            return {"budgets": status}
        if name == "propose_create_budget":
            if "category" not in arguments or "limit_ron" not in arguments:
                raise ToolError("Lipsește categoria sau limita bugetului.")
            limit_minor = _to_minor(arguments["limit_ron"], "limit_ron")
            existing = await _cached_budgets(cache, auth_header)
            action = budget_actions_service.propose_create(
                arguments["category"], limit_minor, arguments.get("name"), existing
            )
            cache.pending_action = action
            return {"proposal": action["summary"], "requires_confirmation": True}
        if name == "propose_update_budget":
            if "target" not in arguments or "new_limit_ron" not in arguments:
                raise ToolError("Lipsește bugetul țintă sau noua limită.")
            new_limit_minor = _to_minor(arguments["new_limit_ron"], "new_limit_ron")
            existing = await _cached_budgets(cache, auth_header)
            action = budget_actions_service.propose_update(arguments["target"], new_limit_minor, existing)
            cache.pending_action = action
            return {"proposal": action["summary"], "requires_confirmation": True}
        if name == "propose_delete_budget":
            if "target" not in arguments:
                raise ToolError("Lipsește bugetul țintă.")
            existing = await _cached_budgets(cache, auth_header)
            action = budget_actions_service.propose_delete(arguments["target"], existing)
            cache.pending_action = action
            return {"proposal": action["summary"], "requires_confirmation": True}
        raise ToolError(f"Tool necunoscut: {name}")
    except ToolError:
        raise
    except (ValueError, TypeError, AttributeError, KeyError) as exc:
        # Orice parametru cu formă neașteptată de la GPT (tip greșit, câmp
        # lipsă neanticipat) devine o eroare curată, dată înapoi modelului
        # ca mesaj de tool — NU un 500 brut care ar întrerupe conversația.
        raise ToolError(f"Nu am putut interpreta parametrii pentru '{name}': {exc}") from exc
