"""Orchestrator SUBȚIRE — un singur loc unde userul întreabă orice, fără
să aleagă manual între MaestroAgent și Support. NU rulează el conversația,
NU e un al treilea agent — doar clasifică fiecare întrebare nouă și spune
frontend-ului către ce pagină s-o trimită (vezi app/services/intent_router.py,
clasificare hibridă: cuvinte-cheie + fallback LLM). Fiecare agent
(MaestroAgent, Support) rămâne exact cum era — niciun cod al lor nu e
atins de fișierul ăsta.

Extern (prin Gateway): POST /api/ai/assistant/classify

Frontend-ul (support.ts::askAgent) apelează /classify la FIECARE mesaj nou
(nu doar primul al unei conversații noi) — dacă userul schimbă subiectul
în mijlocul unei conversații de Support către ceva de buget/prognoză, e
redirecționat automat spre MaestroAgent, nu trebuie să pornească manual o
conversație nouă. Excepție: un mesaj care răspunde la o confirmare
în-curs (pending_action) nu se reclasifică niciodată — ar putea fi
"da"/"nu", nu o întrebare nouă.
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
    agent = await classify_intent(
        payload.message,
        current_agent=payload.current_agent,
        recent_history=payload.recent_history,
    )
    return ClassifyResponse(agent=agent, route=_ROUTES[agent])
