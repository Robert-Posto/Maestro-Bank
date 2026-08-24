"""ai-orchestrator-service — locuiește agenții AI ai MaestroBank, peste
Azure OpenAI.

Doi agenți montați aici, fiecare cu propriul router/agent/tools:
  - Spending + Forecast Agent (vezi app/agents/spending_forecast.py) — RAG,
    forecast/affordability determinist, propose-not-execute pentru bugete.
  - Support Agent (vezi app/agents/support.py) — ajutor cont/card/tranzacții/
    tichete, propose-not-execute pentru scrierea unui tichet.

Niciunul dintre ei NU accesează MongoDB direct — toate datele vin prin API
Gateway (vezi app/tools/*), exact ca un client extern (Angular) ar face.
"""

import logging

from fastapi import FastAPI

from app.config import settings
from app.routers.spending_forecast import router as spending_forecast_router
from app.routers.support import router as support_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [ai-orchestrator-service] %(levelname)s %(message)s")

app = FastAPI(title="MaestroBank AI Orchestrator Service")


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "ai-orchestrator-service",
        "azure_openai_configured": settings.azure_openai_configured,
    }


app.include_router(spending_forecast_router)
app.include_router(support_router)
