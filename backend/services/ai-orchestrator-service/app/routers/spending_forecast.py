"""Rute protejate (JWT) ale agentului Spending + Forecast.

Extern (prin Gateway) devin:
  POST /api/ai/spending-forecast/chat
  POST /api/ai/spending-forecast/actions/confirm
"""

from fastapi import APIRouter, HTTPException, status

from app.agents import spending_forecast as agent
from app.models.spending_forecast import ChatRequest, ConfirmActionRequest, ConfirmActionResponse, SpendingForecastResponse
from app.security import AuthContext, CurrentAuth
from app.services import budget_actions_service
from app.tools.errors import ToolError

router = APIRouter(prefix="/spending-forecast", tags=["spending-forecast"])


@router.post("/chat", response_model=SpendingForecastResponse)
async def chat(payload: ChatRequest, auth: AuthContext = CurrentAuth):
    return await agent.handle_message(auth, payload.message, history=payload.history)


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
