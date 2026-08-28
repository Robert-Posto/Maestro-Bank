"""ai-orchestrator-service — locuiește agenții AI ai MaestroBank, peste
Azure OpenAI.

Doi agenți montați aici, fiecare cu propriul router/agent/tools:
  - Spending + Forecast Agent (vezi app/agents/spending_forecast.py) — RAG,
    forecast/affordability determinist, propose-not-execute pentru bugete.
  - Support Agent (vezi app/agents/support.py) — ajutor cont/card/tranzacții/
    tichete, propose-not-execute pentru scrierea unui tichet.

Plus un orchestrator SUBȚIRE (app/routers/assistant.py) — clasifică prima
întrebare a unei conversații NOI și spune frontend-ului cărui agent îi
aparține, ca userul să nu mai aleagă manual pagina. NU e un al treilea
agent, doar rutare deterministă — cei doi agenți de mai sus rămân complet
neatinși.

Niciunul dintre ei NU accesează MongoDB direct — toate datele de cont vin
prin API Gateway (vezi app/tools/*), exact ca un client extern (Angular)
ar face. Excepția e conversations_db (vezi app/database.py), care ține
DOAR istoricul conversațiilor, nu date financiare/de cont.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.database import close_database_connection, ping_database
from app.routers.assistant import router as assistant_router
from app.routers.speech import router as speech_router
from app.routers.spending_forecast import router as spending_forecast_router
from app.routers.support import router as support_router
from app.services.conversation_service import ensure_conversation_indexes

logging.basicConfig(level=logging.INFO, format="%(asctime)s [ai-orchestrator-service] %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_conversation_indexes()
    yield
    await close_database_connection()


app = FastAPI(title="MaestroBank AI Orchestrator Service", lifespan=lifespan)


@app.get("/health")
async def health_check():
    is_connected = await ping_database()
    return {
        "status": "ok" if is_connected else "error",
        "service": "ai-orchestrator-service",
        "database": "connected" if is_connected else "disconnected",
        "azure_openai_configured": settings.azure_openai_configured,
    }


app.include_router(spending_forecast_router)
app.include_router(support_router)
app.include_router(speech_router)
app.include_router(assistant_router)
