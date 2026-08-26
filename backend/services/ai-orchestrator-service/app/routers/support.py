"""Endpoint-urile Support Agent.

Intern: POST /support, GET/DELETE /support/conversations[/{id}]. Extern,
prin Gateway: POST /api/ai/support, GET/DELETE /api/ai/support/conversations[/{id}]
(vezi backend/gateway/app/routers/proxy.py — service="ai", internal_prefix="").

Authorization e validat AICI (defense in depth, ca la orice alt
microserviciu — vezi app/security.py) și propagat neschimbat de-a lungul
întregului flux, la fiecare tool call către Gateway.
"""

import logging

from fastapi import APIRouter, HTTPException, status
from openai import APIError

from app.models.conversation import ConversationDetail, ConversationSummary, to_detail, to_summary
from app.models.support import ChatRequest, ChatResponse
from app.security import CurrentAuthorization, CurrentUserId
from app.services import conversation_service, support_service

logger = logging.getLogger("ai-orchestrator-service")

router = APIRouter(prefix="/support", tags=["support-agent"])

_AGENT: conversation_service.Agent = "support"


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest, authorization: str = CurrentAuthorization, user_id: str = CurrentUserId
) -> ChatResponse:
    if payload.conversation_id:
        conversation = await conversation_service.get_conversation(user_id, _AGENT, payload.conversation_id)
    else:
        conversation = await conversation_service.create_conversation(user_id, _AGENT, payload.message)

    # ChatRequest(message=..., history=...), NU payload.model_copy(update=...)
    # — model_copy nu re-validează, deci `history` ar rămâne o listă de
    # dict-uri brute, iar run_support_agent (app/agents/support.py:304) face
    # acces pe atribut (`m.role`, `m.content`), nu pe cheie de dict; ar
    # arunca AttributeError. Constructorul explicit forțează validarea
    # Pydantic normală, care transformă dict-urile în ChatMessage.
    history_dicts = conversation_service.to_history_dicts(conversation)
    payload_with_history = ChatRequest(
        message=payload.message,
        history=history_dicts,
        pending_action=payload.pending_action,
        conversation_id=payload.conversation_id,
    )

    try:
        response = await support_service.handle_chat(payload_with_history, authorization)
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
            detail=f"Azure OpenAI a răspuns cu eroare ({type(exc).__name__}). Verifică endpoint/deployment/cheia din .env.",
        ) from exc

    await conversation_service.append_turn(conversation["_id"], payload.message, response.answer, response.model_dump())
    response.conversation_id = str(conversation["_id"])
    return response


@router.get("/conversations", response_model=list[ConversationSummary])
async def list_conversations(user_id: str = CurrentUserId):
    docs = await conversation_service.list_conversations(user_id, _AGENT)
    return [to_summary(d) for d in docs]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: str, user_id: str = CurrentUserId):
    doc = await conversation_service.get_conversation(user_id, _AGENT, conversation_id)
    return to_detail(doc)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conversation_id: str, user_id: str = CurrentUserId):
    await conversation_service.delete_conversation(user_id, _AGENT, conversation_id)
