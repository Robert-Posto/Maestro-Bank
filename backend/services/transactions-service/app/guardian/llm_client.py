"""Wrapper izolat peste SDK-ul Azure OpenAI, doar pentru Guardian — copie
redusă a ai-orchestrator-service/app/llm/azure_openai.py (același SDK,
aceeași detecție de endpoint Foundry "v1"), NU o dependență de acel
serviciu. Guardian rulează în-proces în transactions-service (vezi planul
fazei) — motivul e explicat acolo, nu se repetă aici.

Contract DELIBERAT diferit de ai-orchestrator's chat_completion: acolo o
eroare urcă spre router (userul așteaptă activ un răspuns). Aici NU are
voie să urce niciodată — un apel eșuat trebuie să degradeze spre șablon
(vezi guardian/service.py), nu să lase un background task să crape tăcut."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from openai import AsyncAzureOpenAI, AsyncOpenAI, OpenAIError

from app.config import settings

logger = logging.getLogger("transactions-service")

_MAX_ATTEMPTS = 2  # 1 încercare + 1 reîncercare, per spec ("timeout scurt, o reîncercare, apoi fallback")

_chat_client: AsyncAzureOpenAI | AsyncOpenAI | None = None


def _build_client(endpoint: str, api_key: str) -> AsyncAzureOpenAI | AsyncOpenAI:
    endpoint = endpoint.rstrip("/")
    timeout = settings.guardian_llm_timeout_seconds
    # max_retries=0 — SDK-ul reîncearcă intern implicit (până la 2x), ceea
    # ce s-ar compune cu reîncercarea NOASTRĂ din complete_json (_MAX_
    # ATTEMPTS=2), ducând la timeout*(2+1)*2 ≈ 48s în cel mai rău caz sub
    # o resursă Azure lentă/încărcată — confirmat live (log-uri cu
    # "Retrying request..." interne, urmate de reîncercarea proprie).
    # O singură reîncercare, la nivelul nostru, e suficientă (vezi spec).
    if endpoint.endswith("/openai/v1"):
        return AsyncOpenAI(base_url=endpoint, api_key=api_key, timeout=timeout, max_retries=0)
    return AsyncAzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=settings.azure_openai_api_version,
        timeout=timeout,
        max_retries=0,
    )


def _get_chat_client() -> AsyncAzureOpenAI | AsyncOpenAI | None:
    global _chat_client
    if not settings.azure_openai_configured:
        return None
    if _chat_client is None:
        _chat_client = _build_client(settings.azure_openai_endpoint, settings.azure_openai_api_key)
    return _chat_client


async def complete_json(messages: list[dict[str, Any]]) -> dict | None:
    """Un singur apel de chat completion, cu `response_format` JSON, timeout
    scurt + o reîncercare imediată — apoi None, NICIODATĂ o excepție.
    Apelantul (guardian/service.py) cade pe șablon la orice None. NU logăm
    conținutul mesajelor (pot conține date financiare) — doar metadate."""
    client = _get_chat_client()
    if client is None:
        return None

    for attempt in range(_MAX_ATTEMPTS):
        try:
            response = await client.chat.completions.create(
                model=settings.azure_openai_deployment,
                messages=messages,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                logger.warning("guardian: răspuns LLM nu e un obiect JSON — cad pe șablon")
                return None
            return parsed
        except (OpenAIError, asyncio.TimeoutError) as exc:
            logger.warning("guardian: apel LLM eșuat (încercarea %d/%d): %s", attempt + 1, _MAX_ATTEMPTS, exc)
        except (json.JSONDecodeError, IndexError, AttributeError) as exc:
            logger.warning("guardian: răspuns LLM nu a putut fi parsat — cad pe șablon: %s", exc)
            return None
    return None
