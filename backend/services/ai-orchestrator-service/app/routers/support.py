"""Endpoint-ul Support Agent.

Intern: POST /support. Extern, prin Gateway: POST /api/ai/support (vezi
backend/gateway/app/routers/proxy.py — service="ai", internal_prefix="").

Authorization e validat AICI (defense in depth, ca la orice alt
microserviciu — vezi app/security.py) și propagat neschimbat de-a lungul
întregului flux, la fiecare tool call către Gateway.
"""

import logging

from fastapi import APIRouter, HTTPException, status
from openai import APIError

from app.i18n import translate
from app.models.support import ChatRequest, ChatResponse
from app.security import CurrentAuthorization
from app.services import support_service

logger = logging.getLogger("ai-orchestrator-service")

router = APIRouter(prefix="/support", tags=["support-agent"])


@router.post("", response_model=ChatResponse)
async def chat(payload: ChatRequest, authorization: str = CurrentAuthorization) -> ChatResponse:
    try:
        return await support_service.handle_chat(payload, authorization)
    except RuntimeError as exc:
        # Ridicată de app/llm/azure_openai.py când AZURE_OPENAI_ENDPOINT /
        # AZURE_OPENAI_API_KEY lipsesc — răspuns curat, NU un 500 brut.
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except APIError as exc:
        # Eroare REALĂ de la Azure (endpoint/deployment greșit, cheie
        # invalidă, model indisponibil etc.) — nu propagăm mesajul brut al
        # providerului (poate conține detalii interne), doar tipul erorii.
        logger.error("Azure OpenAI a răspuns cu eroare: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=translate("azureError", error_type=type(exc).__name__),
        ) from exc
