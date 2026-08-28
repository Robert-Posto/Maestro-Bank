"""Wrapper izolat peste SDK-ul Azure OpenAI — restul codului (agenți,
routere, RAG) nu importă niciodată `openai` direct, doar acest modul. Așa
putem schimba SDK-ul/providerul fără să atingem logica de business, și
putem înlocui ușor clientul cu unul fals în teste (vezi tests/conftest.py).

Folosește deployment-urile Azure OpenAI configurate prin env vars — vezi
app/config.py. Nu hardcodează niciun secret.
"""

from __future__ import annotations

import logging
from typing import Any

from openai import AsyncAzureOpenAI, AsyncOpenAI

from app.config import settings

logger = logging.getLogger("ai-orchestrator-service")

_chat_client: AsyncAzureOpenAI | AsyncOpenAI | None = None
_embedding_client: AsyncAzureOpenAI | AsyncOpenAI | None = None


class AzureOpenAINotConfigured(RuntimeError):
    """AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY nu sunt setate."""


class AzureEmbeddingsNotConfigured(RuntimeError):
    """AZURE_OPENAI_EMBEDDING_ENDPOINT / AZURE_OPENAI_EMBEDDING_API_KEY nu sunt setate."""


def _build_client(endpoint: str, api_key: str) -> AsyncAzureOpenAI | AsyncOpenAI:
    endpoint = endpoint.rstrip("/")
    # Timeout explicit PER apel — vezi debugging live: pe resursa Azure
    # folosită (shared, de academy), runda care generează textul final
    # poate ocazional dura 45-60s+ (variabilitate reală de latență, nu un
    # bug de-al nostru — confirmat cu logging pe rundă în app/agents/).
    # Fără timeout explicit, SDK-ul așteaptă implicit până la 10 minute pe
    # apel, ceea ce ar lăsa userul agățat mult peste ce tolerează UI-ul.
    # Cu ăsta, un apel blocat eșuează curat (openai.APITimeoutError,
    # prins în app/agents/spending_forecast.py -> 502 cu mesaj clar) în
    # loc să agațe cererea la infinit.
    timeout = settings.azure_openai_request_timeout_seconds
    if endpoint.endswith("/openai/v1"):
        # Azure AI Foundry — API-ul nou "v1", compatibil direct cu SDK-ul
        # standard `openai` (base_url + api_key, FĂRĂ api_version) — nu cu
        # AzureOpenAI/azure_endpoint (formatul mai vechi). Detectat din
        # forma URL-ului, ca să nu fie nevoie de o variabilă suplimentară.
        return AsyncOpenAI(base_url=endpoint, api_key=api_key, timeout=timeout)
    return AsyncAzureOpenAI(
        azure_endpoint=endpoint, api_key=api_key, api_version=settings.azure_openai_api_version, timeout=timeout
    )


def _get_chat_client() -> AsyncAzureOpenAI | AsyncOpenAI:
    global _chat_client
    if not settings.azure_openai_configured:
        raise AzureOpenAINotConfigured(
            "Azure OpenAI nu este configurat — setează AZURE_OPENAI_ENDPOINT și AZURE_OPENAI_API_KEY."
        )
    if _chat_client is None:
        _chat_client = _build_client(settings.azure_openai_endpoint, settings.azure_openai_api_key)
    return _chat_client


def _get_embedding_client() -> AsyncAzureOpenAI | AsyncOpenAI:
    global _embedding_client
    if not settings.azure_embeddings_configured:
        raise AzureEmbeddingsNotConfigured(
            "Embeddings Azure OpenAI nu sunt configurate — setează "
            "AZURE_OPENAI_EMBEDDING_ENDPOINT și AZURE_OPENAI_EMBEDDING_API_KEY "
            "(sau lasă-le nesetate ca să cadă pe AZURE_OPENAI_ENDPOINT/API_KEY)."
        )
    if _embedding_client is None:
        _embedding_client = _build_client(
            settings.azure_openai_embedding_endpoint, settings.azure_openai_embedding_api_key
        )
    return _embedding_client


async def chat_completion(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    tool_choice: Any = None,
) -> Any:
    """Un singur apel de chat completion (cu/fără tool calling).

    Întoarce obiectul `choices[0].message` brut din SDK — apelantul
    (app/agents/spending_forecast.py) decide ce face cu el (text final sau
    tool_calls de executat). NU logăm niciodată conținutul mesajelor (pot
    conține date financiare ale userului) — doar metadate (nr. mesaje,
    nr. tool-uri disponibile, durata).

    `tool_choice`: implicit "auto" cât timp există `tools` (comportamentul
    de dinainte, neschimbat pentru agenții existenți) — dar apelantul poate
    forța un tool anume (ex. `{"type": "function", "function": {"name": "x"}}`),
    util pentru un apel cu UN SINGUR tool unde răspunsul TREBUIE să fie
    structurat, nu text liber (vezi app/services/intent_router.py).
    """
    client = _get_chat_client()
    response = await client.chat.completions.create(
        model=settings.azure_openai_deployment,
        messages=messages,
        tools=tools,
        tool_choice=tool_choice if tool_choice is not None else ("auto" if tools else None),
    )
    return response.choices[0].message


async def create_embeddings(texts: list[str]) -> list[list[float]]:
    """Embeddings reale (Azure OpenAI `text-embedding-3-small` implicit) —
    folosite de app/rag/retriever.py pentru similaritate semantică, nu doar
    suprapunere de cuvinte (vezi TfidfVectorizer, fallback-ul folosit dacă
    embeddings nu sunt configurate). Întoarce vectorii în aceeași ordine
    cu `texts`.
    """
    if not texts:
        return []
    client = _get_embedding_client()
    response = await client.embeddings.create(model=settings.azure_openai_embedding_deployment, input=texts)
    return [item.embedding for item in response.data]
