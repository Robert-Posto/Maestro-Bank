"""Clasificator de intenție pentru "un singur loc unde întrebi orice" —
vezi app/routers/assistant.py. Hibrid, nu doar cuvinte-cheie:

1. Cale rapidă, GRATUITĂ — dacă mesajul conține clar un cuvânt-cheie de
   buget/prognoză (listă RO+EN, vezi mai jos), răspundem instant, fără apel
   LLM. Corectă mereu când se potrivește (nimeni nu scrie "buget" fără să
   vorbească de fapt despre buget).
2. Altfel, un apel LLM (GPT-5-mini, același model ca cei doi agenți),
   tool-forțat pe un răspuns strict structurat — NU o presupunere pe
   cuvinte-cheie. Versiunea veche (doar regex, fără pasul 2) trata absența
   unui cuvânt-cheie exact ca "sigur Support", ceea ce rata orice formulare
   naturală fără cuvintele exacte ("pot să-mi cumpăr un laptop de 3000?",
   "cât mi-a mai rămas din leafă?", "e prea mult ce dau pe mâncare?") —
   exact genul de întrebări reale pe care userii chiar le pun.

NU inventează o graniță nouă de domeniu — e EXACT aceeași graniță deja
documentată în app/prompts/support_prompt.py (Support Agent redirecționează
explicit userul spre MaestroAgent pentru buget/prognoză/abonamente, spunând
clar "nu tu gestionezi asta"). Aici doar automatizăm decizia, ca userul să
nu mai aleagă manual pagina.

Support Agent rămâne implicit (catch-all) — orice mesaj care NU se
potrivește clar cu domeniul Spending + Forecast merge la Support (fie prin
calea rapidă absentă, fie prin decizia LLM-ului, fie ca fallback dacă
apelul LLM eșuează), exact cum Support e deja domeniul "tot restul" (conturi,
carduri, tranzacții, transferuri, schimb valutar, depozite, investiții,
credite, documente, tichete).

Reclasificare pe parcursul unei conversații deja angajate (`current_agent`
setat): fallback-ul LLM STATELESS original (doar mesajul curent, fără
context) avea o limitare reală, raportată de user — cu contextul absent,
orice follow-up ambiguu fără cuvânt-cheie ("Ce buffer?") risca să fie
clasificat greșit ca schimbare de agent. O primă reparație (vezi git log)
a rezolvat asta oprind complet LLM-ul după primul mesaj — dar simetric,
asta bloca și schimbările REALE de subiect fără cuvânt-cheie exact (ex.
"cât mai am pana la salariu?" în mijlocul unei conversații de Support).
Soluția corectă: LLM-ul rămâne activ pe tot parcursul conversației, dar
primește explicit agentul curent + un istoric scurt, ca să poată judeca
"asta continuă discuția curentă, sau chiar schimbă domeniul?" — vezi
`_classify_by_llm_with_context`.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Literal

from app.llm.azure_openai import AzureOpenAINotConfigured, chat_completion

logger = logging.getLogger("ai-orchestrator-service")

AgentName = Literal["spending_forecast", "support"]

# Fiecare tipar corespunde unui subiect pe care Support Agent ÎL
# REDIRECȚIONEAZĂ deja explicit spre MaestroAgent (vezi support_prompt.py) —
# lista de mai jos NU e o graniță nouă, doar calea rapidă (fără LLM) pentru
# cazurile evidente. RO + EN, fiindcă userul poate scrie în oricare limbă
# (comutatorul de limbă schimbă UI-ul, nu ce tastează userul).
_SPENDING_FORECAST_PATTERNS = [
    # RO
    r"\bbuget\w*",
    r"\bcheltui\w*",
    r"\beconomis\w*",
    r"\b[îi]mi permit\w*",
    r"\bpermite\w* s[ăa]\b",
    r"\bprognoz\w*",
    r"\bforecast\w*",
    r"\babonament\w*",
    # EN
    r"\bbudget\w*",
    r"\bspend\w*",
    r"\bspent\b",
    r"\bsav(?:e|ing)\w*",
    r"\bcan i afford\b",
    r"\bafford\w*",
    r"\bsubscription\w*",
    r"\bcash[- ]?flow\b",
]

_SPENDING_FORECAST_REGEX = re.compile("|".join(_SPENDING_FORECAST_PATTERNS), re.IGNORECASE)

_CLASSIFY_TOOL = {
    "type": "function",
    "function": {
        "name": "select_agent",
        "description": "Alege agentul MaestroBank căruia îi aparține mesajul userului.",
        "parameters": {
            "type": "object",
            "properties": {
                "agent": {
                    "type": "string",
                    "enum": ["spending_forecast", "support"],
                    "description": (
                        "'spending_forecast' DOAR când mesajul e clar despre buget, cheltuieli, "
                        "economii, ce-și poate permite userul, prognoză financiară sau abonamente "
                        "recurente. 'support' pentru absolut orice altceva — cont, card, "
                        "tranzacții, transferuri, schimb valutar, depozite, investiții, "
                        "credite, documente, tichete — sau orice mesaj ambiguu, "
                        "general, un salut, sau care nu se încadrează clar în prima categorie."
                    ),
                },
            },
            "required": ["agent"],
        },
    },
}

_SYSTEM_PROMPT = (
    "Ești un router determinist pentru MaestroBank (bancă demo). Primești UN "
    "singur mesaj al unui client și decizi cărui agent îi aparține, apelând "
    "OBLIGATORIU tool-ul select_agent — niciodată text liber. 'support' e "
    "domeniul implicit (catch-all): alege 'spending_forecast' STRICT când "
    "mesajul e clar despre buget, cheltuieli, economii, ce își permite, sau "
    "prognoză financiară. La orice dubiu, alege 'support'."
)

# Folosit DOAR când conversația e deja angajată cu un agent (current_agent
# setat) — spre deosebire de _SYSTEM_PROMPT (prima întrebare, fără context),
# aici LLM-ul primește explicit agentul curent + un istoric scurt, ca să
# poată distinge o continuare firească (rămâi) de o schimbare reală de
# subiect (comută) — vezi docstring-ul modulului.
_CONTEXT_SYSTEM_PROMPT_TEMPLATE = (
    "Ești un router determinist pentru MaestroBank (bancă demo). Clientul are "
    "deja o conversație în curs cu agentul '{current_agent}'. Vezi mai jos "
    "istoricul recent al conversației, urmat de mesajul nou al clientului. "
    "Apelează OBLIGATORIU tool-ul select_agent — niciodată text liber. Alege "
    "'spending_forecast' STRICT dacă mesajul nou introduce clar un subiect "
    "de buget, cheltuieli, economii, ce își permite clientul, sau prognoză "
    "financiară — DIFERIT de ce se discută deja. Alege 'support' STRICT dacă "
    "mesajul nou introduce clar un subiect de cont, card, tranzacții, "
    "transferuri, schimb valutar, depozite, investiții, credite, documente "
    "sau tichete — DIFERIT de ce se discută deja. Dacă mesajul doar "
    "continuă, clarifică sau răspunde la discuția curentă — chiar și fără "
    "niciun cuvânt-cheie explicit — alege '{current_agent}'. NU schimba "
    "agentul fără un semnal clar de subiect nou."
)


def _classify_by_keywords(message: str) -> AgentName | None:
    """Calea rapidă, fără LLM. Întoarce None dacă nu e clar — caz în care
    classify_intent trece la LLM, NU presupune automat "support" (asta era
    limitarea versiunii vechi)."""
    if _SPENDING_FORECAST_REGEX.search(message):
        return "spending_forecast"
    return None


async def _classify_by_llm(message: str) -> AgentName:
    """Fallback pentru mesajele fără o potrivire clară de cuvinte-cheie —
    un singur apel ieftin (GPT-5-mini), tool-forțat pe un răspuns strict
    structurat. Orice eșec (Azure neconfigurat, timeout, răspuns
    neașteptat) cade sigur pe "support" — niciodată nu blochează userul."""
    try:
        response_message = await chat_completion(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ],
            tools=[_CLASSIFY_TOOL],
            tool_choice={"type": "function", "function": {"name": "select_agent"}},
        )
        tool_calls = getattr(response_message, "tool_calls", None)
        if tool_calls:
            args = json.loads(tool_calls[0].function.arguments)
            agent = args.get("agent")
            if agent in ("spending_forecast", "support"):
                return agent
    except AzureOpenAINotConfigured:
        logger.info("Azure OpenAI neconfigurat — clasificare pe 'support' (catch-all).")
    except Exception:
        # NU logăm mesajul userului (poate conține date financiare) — doar
        # faptul că apelul a eșuat.
        logger.warning("Clasificare LLM eșuată — cad pe 'support' (catch-all).", exc_info=True)

    return "support"


async def _classify_by_llm_with_context(
    message: str, current_agent: AgentName, recent_history: list[str]
) -> AgentName:
    """Reclasificare pe parcursul unei conversații deja angajate — spre
    deosebire de `_classify_by_llm` (stateless, doar pentru prima
    întrebare), aici LLM-ul vede și agentul curent, și un istoric scurt, ca
    să poată distinge o continuare firească de o schimbare reală de
    subiect. Orice eșec (Azure neconfigurat, timeout) cade sigur pe
    `current_agent` — RĂMÂNEM pe agentul deja angajat, nu pe "support" —
    o eroare de rețea nu trebuie să arate ca o decizie de rutare."""
    history_text = "\n".join(recent_history) if recent_history else "(fără istoric)"
    user_content = f"Istoric recent:\n{history_text}\n\nMesaj nou al clientului: {message}"
    try:
        response_message = await chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": _CONTEXT_SYSTEM_PROMPT_TEMPLATE.format(current_agent=current_agent),
                },
                {"role": "user", "content": user_content},
            ],
            tools=[_CLASSIFY_TOOL],
            tool_choice={"type": "function", "function": {"name": "select_agent"}},
        )
        tool_calls = getattr(response_message, "tool_calls", None)
        if tool_calls:
            args = json.loads(tool_calls[0].function.arguments)
            agent = args.get("agent")
            if agent in ("spending_forecast", "support"):
                return agent
    except AzureOpenAINotConfigured:
        logger.info("Azure OpenAI neconfigurat — rămânem pe agentul curent (%s).", current_agent)
    except Exception:
        # NU logăm mesajul userului (poate conține date financiare) — doar
        # faptul că apelul a eșuat.
        logger.warning("Reclasificare cu context eșuată — rămânem pe agentul curent.", exc_info=True)

    return current_agent


async def classify_intent(
    message: str,
    *,
    current_agent: AgentName | None = None,
    recent_history: list[str] | None = None,
) -> AgentName:
    """"spending_forecast" dacă mesajul ține clar de buget/cheltuieli/
    economii/prognoză, altfel "support" (domeniul implicit, catch-all).
    Vezi docstring-ul modulului pentru calea rapidă vs. LLM.

    `current_agent=None` — prima întrebare a unei conversații NOI, fără
    niciun context anterior: clasificare hibridă completă (cuvinte-cheie,
    apoi LLM stateless dacă e nevoie).

    `current_agent` setat — un mesaj care CONTINUĂ o conversație deja
    angajată cu agentul respectiv: fără o potrivire clară de cuvinte-cheie,
    LLM-ul e consultat DIN NOU, dar de data asta cu context (agentul curent
    + `recent_history`), ca să poată distinge o continuare firească de o
    schimbare reală de subiect — vezi `_classify_by_llm_with_context`."""
    fast = _classify_by_keywords(message)
    if fast is not None:
        return fast
    if current_agent is None:
        return await _classify_by_llm(message)
    return await _classify_by_llm_with_context(message, current_agent, recent_history or [])
