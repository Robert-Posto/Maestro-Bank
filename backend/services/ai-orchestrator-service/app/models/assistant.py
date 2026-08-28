"""DTO-uri pentru orchestrator-ul subțire — vezi app/routers/assistant.py.
NU e un al treilea agent — doar clasifică o întrebare NOUĂ și spune
frontend-ului cărei pagini (MaestroAgent sau Support) îi aparține."""

from pydantic import BaseModel, Field

from app.services.intent_router import AgentName


class ClassifyRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ClassifyResponse(BaseModel):
    agent: AgentName
    route: str
