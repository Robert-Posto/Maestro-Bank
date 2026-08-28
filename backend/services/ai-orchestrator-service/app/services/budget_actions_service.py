"""Logică determinist pentru acțiuni asupra bugetelor (creare/modificare/
ștergere) — cu un principiu STRICT, cerut explicit:

    GPT PROPUNE (validare + interpretare), NU EXECUTĂ.

`propose_create` / `propose_update` / `propose_delete` de mai jos sunt
funcții PURE (fără I/O) apelate din interiorul tool-calling-ului GPT (vezi
app/tools/registry.py) — construiesc o acțiune complet specificată și
validată, dar NU o trimit mai departe la budgets-service. Rezultatul
ajunge în DTO ca `pending_action`, userul vede un buton de confirmare
explicit în UI, și DOAR atunci se apelează `execute_confirmed_action` de
mai jos — un apel simplu, determinist, FĂRĂ niciun GPT în buclă (vezi
app/routers/spending_forecast.py::confirm_action).
"""

from __future__ import annotations

from app.i18n import pick
from app.services.affordability_service import format_ron
from app.tools import budgets_tools
from app.tools.errors import ToolError

# Categoriile valide pentru un buget — identice cu TRANSACTION_CATEGORIES
# din transactions-service/app/models.py, minus "income" (n-are sens un
# buget de venit).
VALID_BUDGET_CATEGORIES = {
    "groceries",
    "shopping",
    "transport",
    "bills",
    "restaurants",
    "entertainment",
    "subscriptions",
    "other",
}


def find_budget(budgets: list[dict], query: str) -> dict | None:
    """Caută UN buget activ, după nume SAU categorie (potrivire exactă,
    fără majuscule). Dacă e ambiguu (0 sau 2+ potriviri), întoarce None —
    NU ghicim niciodată care buget a vrut userul; GPT trebuie să ceară
    clarificare (vezi ToolError-urile din propose_update/propose_delete).
    """
    normalized = query.strip().lower()
    matches = [
        budget
        for budget in budgets
        if budget.get("active", True)
        and (budget["name"].strip().lower() == normalized or budget["category"].strip().lower() == normalized)
    ]
    return matches[0] if len(matches) == 1 else None


def _active_budget_names(budgets: list[dict]) -> str:
    names = [f"„{b['name']}”" for b in budgets if b.get("active", True)]
    return ", ".join(names) if names else "niciunul"


def propose_create(category: str, limit_minor: int, name: str | None, existing_budgets: list[dict]) -> dict:
    normalized_category = category.strip().lower()
    if normalized_category not in VALID_BUDGET_CATEGORIES:
        raise ToolError(
            f"Categorie necunoscută „{category}”. Categorii valide: {', '.join(sorted(VALID_BUDGET_CATEGORIES))}."
        )
    if limit_minor <= 0:
        raise ToolError("Limita bugetului trebuie să fie un număr pozitiv.")
    if any(
        b.get("active", True) and b["category"].strip().lower() == normalized_category for b in existing_budgets
    ):
        raise ToolError(
            f"Există deja un buget activ pentru categoria „{normalized_category}” — "
            "cere-i userului să-l modifice pe acela, nu crea unul nou."
        )

    budget_name = (name or normalized_category).strip().capitalize()
    payload = {"name": budget_name, "category": normalized_category, "limit_minor": limit_minor, "period": "monthly"}
    limit_text = format_ron(limit_minor)
    summary = pick(
        f"Creez bugetul „{budget_name}” — {limit_text} / lună (categorie: {normalized_category}).",
        f'I\'ll create the "{budget_name}" budget — {limit_text} / month (category: {normalized_category}).',
    )
    return {"type": "create_budget", "summary": summary, "payload": payload}


def propose_update(target: str, new_limit_minor: int, existing_budgets: list[dict]) -> dict:
    budget = find_budget(existing_budgets, target)
    if budget is None:
        raise ToolError(
            f"Nu am găsit un singur buget activ pentru „{target}”. "
            f"Bugetele active sunt: {_active_budget_names(existing_budgets)}."
        )
    if new_limit_minor <= 0:
        raise ToolError("Noua limită trebuie să fie un număr pozitiv.")

    payload = {"budget_id": budget["id"], "limit_minor": new_limit_minor}
    new_text = format_ron(new_limit_minor)
    old_text = format_ron(budget["limit_minor"])
    summary = pick(
        f"Modific bugetul „{budget['name']}” la {new_text} / lună (era {old_text}).",
        f'I\'ll change the "{budget["name"]}" budget to {new_text} / month (was {old_text}).',
    )
    return {"type": "update_budget", "summary": summary, "payload": payload}


def propose_delete(target: str, existing_budgets: list[dict]) -> dict:
    budget = find_budget(existing_budgets, target)
    if budget is None:
        raise ToolError(
            f"Nu am găsit un singur buget activ pentru „{target}”. "
            f"Bugetele active sunt: {_active_budget_names(existing_budgets)}."
        )

    payload = {"budget_id": budget["id"]}
    limit_text = format_ron(budget["limit_minor"])
    summary = pick(
        f"Șterg bugetul „{budget['name']}” ({limit_text} / lună).",
        f'I\'ll delete the "{budget["name"]}" budget ({limit_text} / month).',
    )
    return {"type": "delete_budget", "summary": summary, "payload": payload}


async def execute_confirmed_action(action_type: str, payload: dict, authorization_header: str) -> dict:
    """Execuția REALĂ — apelată STRICT după ce userul apasă "Confirmă" în
    UI (vezi app/routers/spending_forecast.py::confirm_action). Fără GPT
    în buclă: doar validare + un apel HTTP determinist către budgets-service.
    """
    if action_type == "create_budget":
        name = payload.get("name")
        category = payload.get("category")
        limit_minor = payload.get("limit_minor")
        if not name or not category or not limit_minor:
            raise ToolError(
                pick(
                    "Datele acțiunii sunt incomplete (lipsește nume, categorie sau limită).",
                    "The action data is incomplete (missing name, category or limit).",
                )
            )
        budget = await budgets_tools.create_budget(
            {"name": name, "category": category, "limit_minor": limit_minor, "period": payload.get("period", "monthly")},
            authorization_header,
        )
        return {
            "success": True,
            "message": pick(f"Bugetul „{budget['name']}” a fost creat.", f'The "{budget["name"]}" budget was created.'),
            "budget": budget,
        }

    if action_type == "update_budget":
        budget_id = payload.get("budget_id")
        if not budget_id:
            raise ToolError(pick("Lipsește identificatorul bugetului de modificat.", "Missing the budget ID to update."))
        fields = {key: value for key, value in payload.items() if key != "budget_id"}
        if not fields:
            raise ToolError(pick("Nu există nimic de modificat.", "There is nothing to update."))
        budget = await budgets_tools.update_budget(budget_id, fields, authorization_header)
        return {
            "success": True,
            "message": pick(
                f"Bugetul „{budget['name']}” a fost actualizat.", f'The "{budget["name"]}" budget was updated.'
            ),
            "budget": budget,
        }

    if action_type == "delete_budget":
        budget_id = payload.get("budget_id")
        if not budget_id:
            raise ToolError(pick("Lipsește identificatorul bugetului de șters.", "Missing the budget ID to delete."))
        await budgets_tools.delete_budget(budget_id, authorization_header)
        return {"success": True, "message": pick("Bugetul a fost șters.", "The budget was deleted."), "budget": None}

    raise ToolError(pick(f"Tip de acțiune necunoscut: {action_type}", f"Unknown action type: {action_type}"))
