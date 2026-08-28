"""Teste pentru orchestrator-ul subțire (clasificare + rutare) — vezi
app/services/intent_router.py, app/routers/assistant.py.

Rulare (din interiorul containerului ai-orchestrator-service):

    docker compose exec ai-orchestrator-service pip install -r requirements-dev.txt -q
    docker compose exec ai-orchestrator-service python -m pytest -q
"""

import pytest
from httpx import AsyncClient

from app.services.intent_router import classify_intent

# --- classify_intent — pură, fără DB/HTTP -----------------------------------------


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
def test_classify_intent_routes_budget_questions_to_spending_forecast(message: str):
    assert classify_intent(message) == "spending_forecast"


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
def test_classify_intent_defaults_unmatched_messages_to_support(message: str):
    assert classify_intent(message) == "support"


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


async def test_classify_endpoint_routes_account_question_to_support(client: AsyncClient, support_auth_header: dict[str, str]):
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
