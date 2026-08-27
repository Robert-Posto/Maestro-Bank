"""Rute protejate (JWT) ale agentului Spending + Forecast.

Extern (prin Gateway) devin:
  POST   /api/ai/spending-forecast/chat
  POST   /api/ai/spending-forecast/actions/confirm
  GET    /api/ai/spending-forecast/conversations
  GET    /api/ai/spending-forecast/conversations/{conversation_id}
  DELETE /api/ai/spending-forecast/conversations/{conversation_id}
"""

from fastapi import APIRouter, HTTPException, status

from app.agents import spending_forecast as agent
from app.models.conversation import ConversationDetail, ConversationSummary, to_detail, to_summary
from app.models.spending_forecast import (
    ChatHistoryMessage,
    ChatRequest,
    ConfirmActionRequest,
    ConfirmActionResponse,
    SpendingForecastResponse,
)
from app.security import AuthContext, CurrentAuth
from app.services import budget_actions_service, conversation_service
from app.tools.errors import ToolError

router = APIRouter(prefix="/spending-forecast", tags=["spending-forecast"])

_AGENT: conversation_service.Agent = "spending_forecast"


@router.post("/chat", response_model=SpendingForecastResponse)
async def chat(payload: ChatRequest, auth: AuthContext = CurrentAuth):
    if payload.conversation_id:
        conversation = await conversation_service.get_conversation(auth.user_id, _AGENT, payload.conversation_id)
    else:
        conversation = await conversation_service.create_conversation(auth.user_id, _AGENT, payload.message)

    history = [ChatHistoryMessage(**m) for m in conversation_service.to_history_dicts(conversation)]
    response = await agent.handle_message(auth, payload.message, history=history)

    await conversation_service.append_turn(conversation["_id"], payload.message, response.answer, response.model_dump())
    response.conversation_id = str(conversation["_id"])
    return response


@router.post("/actions/confirm", response_model=ConfirmActionResponse)
async def confirm_action(payload: ConfirmActionRequest, auth: AuthContext = CurrentAuth):
    """Execuția REALĂ a unei acțiuni de buget PROPUSE anterior de agent
    (vezi `pending_action` din răspunsul de chat) — apelată STRICT după ce
    userul apasă explicit "Confirmă" în UI. NU trece prin GPT — e un apel
    determinist, direct, către budgets-service prin Gateway.
    """
    try:
        result = await budget_actions_service.execute_confirmed_action(payload.type, payload.payload, auth.authorization_header)
    except ToolError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return ConfirmActionResponse(**result)


@router.get("/conversations", response_model=list[ConversationSummary])
async def list_conversations(auth: AuthContext = CurrentAuth):
    docs = await conversation_service.list_conversations(auth.user_id, _AGENT)
    return [to_summary(d) for d in docs]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: str, auth: AuthContext = CurrentAuth):
    doc = await conversation_service.get_conversation(auth.user_id, _AGENT, conversation_id)
    return to_detail(doc)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conversation_id: str, auth: AuthContext = CurrentAuth):
    await conversation_service.delete_conversation(auth.user_id, _AGENT, conversation_id)
