"""ai-orchestrator-service — locuiește agenții AI ai MaestroBank.

Primul agent implementat: Support Agent (vezi app/agents/support.py).
Structura e pregătită pentru alți agenți viitori (Spending + Forecast,
Budget, Guardian), fiecare cu propriul router/agent/tools, montați aici
alături de support_router — NU implementat în acest branch.

Support Agent NU are bază de date proprie — nu accesează MongoDB direct,
vorbește EXCLUSIV cu restul sistemului prin API Gateway (vezi app/tools/).
"""

import logging

from fastapi import FastAPI

from app.config import settings
from app.routers.support import router as support_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [ai-orchestrator-service] %(levelname)s %(message)s")

app = FastAPI(title="MaestroBank AI Orchestrator")
app.include_router(support_router)


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "ai-orchestrator-service",
        "azure_openai_configured": bool(settings.azure_openai_endpoint and settings.azure_openai_api_key),
    }
