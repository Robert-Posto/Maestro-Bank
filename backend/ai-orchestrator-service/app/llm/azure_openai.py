"""Wrapper subțire peste Azure OpenAI (GPT-5-mini).

Singurul loc din ai-orchestrator-service care importă SDK-ul `openai` —
restul codului (app/agents/support.py) depinde doar de metoda
`complete()` de mai jos, ca să poată fi înlocuită ușor cu o dublură de
test (vezi tests/conftest.py::FakeLLMClient), fără nicio cheie Azure
reală și fără niciun apel de rețea în teste.

Dacă branch-ul Spending + Forecast introduce propriul
`llm/azure_openai.py` cu o interfață compatibilă (o metodă async
`complete(messages, tools)` care întoarce mesajul brut al modelului),
acest fișier poate fi înlocuit cu acela după merge, fără să schimbe
app/agents/support.py.

NU loghează niciodată API key-ul. Configurația vine STRICT din variabile
de mediu (vezi app/config.py) — nimic hardcodat.

NOTĂ despre client: folosim `AsyncOpenAI` (client OpenAI simplu, NU
`AsyncAzureOpenAI`), cu `base_url` = endpoint-ul Azure AI Foundry care se
termină în `/openai/v1` — asta e suprafața de API unificată, compatibilă
OpenAI, pe care o expun resursele Foundry (spre deosebire de endpoint-ul
Azure OpenAI "clasic", fără `/openai/v1`, folosit de `AsyncAzureOpenAI`,
care construiește alt path și primește 404 pe un endpoint Foundry).
`AZURE_OPENAI_DEPLOYMENT` devine `model` la apel, exact ca la OpenAI direct.
"""

from typing import Any

from openai import AsyncOpenAI

from app.config import settings


class AzureOpenAIClient:
    """Interfața minimă de care are nevoie orchestratorul de tool-calling."""

    def __init__(self) -> None:
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            if not settings.azure_openai_endpoint or not settings.azure_openai_api_key:
                raise RuntimeError(
                    "Azure OpenAI nu e configurat — setează AZURE_OPENAI_ENDPOINT și "
                    "AZURE_OPENAI_API_KEY (vezi .env.example)."
                )
            self._client = AsyncOpenAI(
                base_url=settings.azure_openai_endpoint,
                api_key=settings.azure_openai_api_key,
            )
        return self._client

    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Any:
        """Un singur turn de chat completion cu tool-calling. Întoarce
        mesajul brut de răspuns al SDK-ului — apelantul decide cum să-l
        interpreteze (tool_calls vs content simplu)."""
        client = self._get_client()
        response = await client.chat.completions.create(
            model=settings.azure_openai_deployment,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
        return response.choices[0].message


azure_openai_client = AzureOpenAIClient()
