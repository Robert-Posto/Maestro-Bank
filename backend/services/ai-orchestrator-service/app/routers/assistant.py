"""Orchestrator SUBȚIRE — un singur loc unde userul întreabă orice, fără
să aleagă manual între MaestroAgent și Support. NU rulează el conversația,
NU e un al treilea agent — doar clasifică prima întrebare a unei
conversații NOI și spune frontend-ului către ce pagină s-o trimită
(vezi app/services/intent_router.py). Fiecare agent (MaestroAgent, Support)
rămâne exact cum era — niciun cod al lor nu e atins de fișierul ăsta.

Extern (prin Gateway): POST /api/ai/assistant/classify

O conversație deja începută NU se reclasifică — userul care schimbă
subiectul pornește pur și simplu o conversație nouă (butonul deja existent
"Conversație nouă" din header-ul fiecărei pagini de chat), exact cum
funcționează deja azi.
"""

from fastapi import APIRouter

from app.models.assistant import ClassifyRequest, ClassifyResponse
from app.security import CurrentUserId
from app.services.intent_router import classify_intent

router = APIRouter(prefix="/assistant", tags=["assistant"])

# Rutele REALE Angular, rezolvate determinist aici — frontend-ul primește
# direct unde să navigheze, nu doar numele agentului (deși primește și pe
# ăla, pt un eventual label "răspunde MaestroAgent/Support").
_ROUTES: dict[str, str] = {
    "spending_forecast": "/app/copilot",
    "support": "/app/support",
}


@router.post("/classify", response_model=ClassifyResponse)
async def classify_route(payload: ClassifyRequest, user_id: str = CurrentUserId):
    agent = classify_intent(payload.message)
    return ClassifyResponse(agent=agent, route=_ROUTES[agent])
