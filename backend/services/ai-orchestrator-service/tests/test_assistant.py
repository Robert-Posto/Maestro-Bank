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


# --- classify_intent — fallback LLM (mesaje fără cuvânt-cheie clar) ----------------


@pytest.mark.parametrize(
    "message",
    [
        "Cardul meu e activ?",
        "De ce mi-a fost reținut transferul de ieri?",
        "Vreau să deschid un cont de economii",
        "Cât mai am de plătit la creditul meu?",
        "Ce puncte am acumulat luna asta?",
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
    """Azure OpenAI neconfigurat (sau orice eroare) — nu blochează userul,
    cade sigur pe domeniul implicit (support)."""
    monkeypatch.setattr("app.services.intent_router.chat_completion", _fake_classify_llm_unavailable())
    assert await classify_intent("Ce mai știi despre bani?") == "support"


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
