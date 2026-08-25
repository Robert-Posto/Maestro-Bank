"""Rută protejată (JWT) pentru text-to-speech — vezi app/tts.py.

Extern (prin Gateway) devine: POST /api/ai/speech

Comună ambilor agenți (MaestroAssistent + Support Agent) — text-to-speech
nu are nicio logică specifică unui agent, doar primește text și întoarce
audio, de-aia stă separat de routers/spending_forecast.py și routers/support.py.
"""

import logging

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response

from app import tts
from app.models.speech import SpeechRequest
from app.security import AuthContext, CurrentAuth

logger = logging.getLogger("ai-orchestrator-service")

router = APIRouter(prefix="/speech", tags=["speech"])


@router.post("")
async def synthesize(payload: SpeechRequest, auth: AuthContext = CurrentAuth):
    """`auth` e cerut DOAR pentru autentificare (nu accesează niciun cont) —
    la fel ca restul rutelor protejate din acest serviciu, ca endpoint-ul
    să nu poată fi apelat neautentificat (ar însemna generare audio
    gratuită, nelimitată, pentru oricine)."""
    try:
        audio = await tts.synthesize_speech(payload.text)
    except Exception as exc:
        logger.warning("ai-orchestrator-service: sinteza vocală a eșuat (user_id=%s)", auth.user_id)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Sinteza vocală a eșuat momentan.") from exc

    return Response(content=audio, media_type="audio/mpeg")
