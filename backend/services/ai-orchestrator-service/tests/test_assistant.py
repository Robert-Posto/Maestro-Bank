"""Teste pentru orchestrator-ul subțire (clasificare + rutare) — vezi
app/services/intent_router.py, app/routers/assistant.py.

Rulare (din interiorul containerului ai-orchestrator-service):

    docker compose exec ai-orchestrator-service pip install -r requirements-dev.txt -q
    docker compose exec ai-orchestrator-service python -m pytest -q
"""

import pytest
from httpx import AsyncClient

from app.llm.azure_openai import AzureOpenAINotConfigured
from app.services.intent_router import classify_intent
from tests.conftest import FakeMessage, make_tool_call


def _fake_classify_llm(agent: str):
    """Simulează chat_completion pentru calea LLM (fallback) —
    classify_intent apelează OBLIGATORIU cu tool_choice forțat pe
    select_agent, deci fake-ul acceptă (și ignoră) parametrul, exact ca
    apelul real."""

    async def fake(messages, tools=None, tool_choice=None):
        return FakeMessage(tool_calls=[make_tool_call("select_agent", {"agent": agent})])

    return fake


def _fake_classify_llm_unavailable():
    async def fake(messages, tools=None, tool_choice=None):
        raise AzureOpenAINotConfigured("test")

    return fake


# --- classify_intent — calea rapidă (cuvinte-cheie, fără LLM) ----------------------


@pytest.mark.parametrize(
    "message",
    [
        "Îmi permit un city break de 2000 lei luna asta?",
        "Cât am cheltuit luna asta?",
        "Vreau să-mi fac un buget pentru groceries",
        "Cu cât estimezi că rămân la finalul lunii? o prognoză te rog",
        "Am vreun abonament pe care îl plătesc degeaba?",
        "Pot să economisesc mai mult luna viitoare?",
    ],
)
async def test_classify_intent_fast_path_routes_budget_questions(message: str, monkeypatch):
    # NU mock-uim chat_completion — mesajele astea conțin toate un cuvânt-
    # cheie clar, deci calea rapidă răspunde fără niciun apel LLM. Dacă
    # implementarea ar ajunge totuși să apeleze LLM-ul, testul ar pica (nimic
    # mock-uit -> AzureOpenAINotConfigured -> "support", nu "spending_forecast").
    assert await classify_intent(message) == "spending_forecast"


# --- classify_intent — fallback LLM, conversație NOUĂ (current_agent=None) --------


@pytest.mark.parametrize(
    "message",
    [
        "Cardul meu e activ?",
        "De ce mi-a fost reținut transferul de ieri?",
        "Vreau să deschid un cont de economii",
        "Cât mai am de plătit la creditul meu?",
        "Am un document de semnat?",
        "Bună ziua",
    ],
)
async def test_classify_intent_llm_fallback_defaults_to_support(message: str, monkeypatch):
    # Fără cuvânt-cheie clar -> calea rapidă întoarce None -> LLM decide.
    # Scriptăm LLM-ul (mock-uit) să răspundă "support" — testul verifică
    # cablajul (rezultatul LLM-ului ajunge corect la apelant), nu judecata
    # reală a modelului (netestabilă fără un apel real).
    monkeypatch.setattr("app.services.intent_router.chat_completion", _fake_classify_llm("support"))
    assert await classify_intent(message) == "support"


async def test_classify_intent_llm_fallback_can_route_to_spending_forecast(monkeypatch):
    """Mesaj fără niciun cuvânt-cheie exact, dar clar despre finanțe
    personale — exact genul de caz pe care vechiul clasificator (doar
    regex) îl rata sistematic; acum LLM-ul poate corecta."""
    monkeypatch.setattr("app.services.intent_router.chat_completion", _fake_classify_llm("spending_forecast"))
    assert await classify_intent("Pot să-mi cumpăr un laptop de 3000 de lei luna asta?") == "spending_forecast"


async def test_classify_intent_falls_back_to_support_when_llm_unavailable(monkeypatch):
    """Azure OpenAI neconfigurat (sau orice eroare), conversație NOUĂ — nu
    blochează userul, cade sigur pe domeniul implicit (support)."""
    monkeypatch.setattr("app.services.intent_router.chat_completion", _fake_classify_llm_unavailable())
    assert await classify_intent("Ce mai știi despre bani?") == "support"


# --- classify_intent — current_agent setat (mesaj care CONTINUĂ o conversație -----
# --- deja angajată) — vezi bug-ul raportat: "Ce buffer?" / rerutare ratată --------


async def test_classify_intent_with_current_agent_still_calls_llm_with_context(monkeypatch):
    """Spre deosebire de vechiul allow_llm_fallback=False, un follow-up FĂRĂ
    cuvânt-cheie tot ajunge la LLM — dar cu context (agent curent +
    istoric), nu stateless. Aici scriptăm LLM-ul să confirme continuarea."""
    calls: list[dict] = []

    async def fake(messages, tools=None, tool_choice=None):
        calls.append({"messages": messages})
        return FakeMessage(tool_calls=[make_tool_call("select_agent", {"agent": "spending_forecast"})])

    monkeypatch.setattr("app.services.intent_router.chat_completion", fake)
    result = await classify_intent(
        "Ce buffer?",
        current_agent="spending_forecast",
        recent_history=["Client: îmi permit o vacanță de 2000 lei?", "Agent: da, ai un buffer de 500 lei."],
    )
    assert result == "spending_forecast"
    assert len(calls) == 1
    # Contextul (agentul curent + istoricul) chiar ajunge în promptul trimis
    # LLM-ului — altfel n-are de unde să judece o continuare vs. o schimbare.
    system_content = calls[0]["messages"][0]["content"]
    user_content = calls[0]["messages"][1]["content"]
    assert "spending_forecast" in system_content
    assert "buffer de 500 lei" in user_content


async def test_classify_intent_with_current_agent_can_switch_without_keyword(monkeypatch):
    """Bug-ul raportat: pornind conversația cu Support, o întrebare care
    ține de fapt de MaestroAgent dar FĂRĂ cuvânt-cheie exact trebuie
    reclasificată — nu mai rămâne blocată pe Support la nesfârșit."""
    monkeypatch.setattr("app.services.intent_router.chat_completion", _fake_classify_llm("spending_forecast"))
    result = await classify_intent(
        "cât mai am pana la salariu?",
        current_agent="support",
        recent_history=["Client: cardul meu e activ?", "Agent: da, cardul tău e activ."],
    )
    assert result == "spending_forecast"


async def test_classify_intent_with_current_agent_stays_on_llm_failure(monkeypatch):
    """Eroare la reclasificare (Azure jos etc.) — rămânem pe agentul DEJA
    angajat, nu pe "support" implicit (spre deosebire de o conversație nouă,
    aici există deja un agent activ, iar o eroare de rețea nu trebuie să
    arate ca o decizie de rutare)."""
    monkeypatch.setattr("app.services.intent_router.chat_completion", _fake_classify_llm_unavailable())
    result = await classify_intent("Ce mai zici?", current_agent="spending_forecast", recent_history=[])
    assert result == "spending_forecast"


async def test_classify_intent_with_current_agent_still_uses_fast_path(monkeypatch):
    """Un mesaj cu un cuvânt-cheie clar tot declanșează spending_forecast
    instant, chiar cu current_agent setat — calea rapidă nu depinde de LLM."""

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("LLM-ul nu trebuia apelat pentru un mesaj cu cuvânt-cheie clar")

    monkeypatch.setattr("app.services.intent_router.chat_completion", fail_if_called)
    result = await classify_intent("Ce buget mai am?", current_agent="support", recent_history=[])
    assert result == "spending_forecast"


# --- Endpoint HTTP -----------------------------------------------------------------


async def test_classify_endpoint_requires_auth(client: AsyncClient):
    response = await client.post("/assistant/classify", json={"message": "Cardul meu e activ?"})
    assert response.status_code == 401


async def test_classify_endpoint_routes_budget_question_to_copilot(client: AsyncClient, support_auth_header: dict[str, str]):
    response = await client.post(
        "/assistant/classify", json={"message": "Îmi permit o vacanță de 3000 lei?"}, headers=support_auth_header
    )
    assert response.status_code == 200
    body = response.json()
    assert body["agent"] == "spending_forecast"
    assert body["route"] == "/app/copilot"


async def test_classify_endpoint_routes_account_question_to_support(
    client: AsyncClient, support_auth_header: dict[str, str], monkeypatch
):
    monkeypatch.setattr("app.services.intent_router.chat_completion", _fake_classify_llm("support"))
    response = await client.post(
        "/assistant/classify", json={"message": "Cardul meu e blocat?"}, headers=support_auth_header
    )
    assert response.status_code == 200
    body = response.json()
    assert body["agent"] == "support"
    assert body["route"] == "/app/support"


async def test_classify_endpoint_rejects_empty_message(client: AsyncClient, support_auth_header: dict[str, str]):
    response = await client.post("/assistant/classify", json={"message": ""}, headers=support_auth_header)
    assert response.status_code == 422


async def test_classify_endpoint_reroutes_with_current_agent_and_no_keyword(
    client: AsyncClient, support_auth_header: dict[str, str], monkeypatch
):
    """"cât mai am pana la salariu?" prin endpoint-ul real, cu
    current_agent="support" — trebuie să poată reclasifica spre
    spending_forecast FĂRĂ niciun cuvânt-cheie exact (bug-ul raportat)."""
    monkeypatch.setattr("app.services.intent_router.chat_completion", _fake_classify_llm("spending_forecast"))
    response = await client.post(
        "/assistant/classify",
        json={
            "message": "cât mai am pana la salariu?",
            "current_agent": "support",
            "recent_history": ["Client: cardul meu e activ?", "Agent: da."],
        },
        headers=support_auth_header,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["agent"] == "spending_forecast"
    assert body["route"] == "/app/copilot"
