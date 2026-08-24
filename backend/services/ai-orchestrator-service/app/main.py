"""ai-orchestrator-service — agenți AI MaestroBank, peste Azure OpenAI.

În acest branch: DOAR agentul Spending + Forecast (vezi
app/agents/spending_forecast.py). Read-only — nu execută transferuri, nu
modifică bugete/carduri/conturi. NU accesează MongoDB — toate datele vin
prin API Gateway (vezi app/tools/*).
"""

import logging

from fastapi import FastAPI

from app.config import settings
from app.routers.spending_forecast import router as spending_forecast_router

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
