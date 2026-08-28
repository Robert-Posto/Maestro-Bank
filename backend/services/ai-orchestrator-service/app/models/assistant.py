"""DTO-uri pentru orchestrator-ul subțire — vezi app/routers/assistant.py.
NU e un al treilea agent — doar clasifică o întrebare NOUĂ și spune
frontend-ului cărei pagini (MaestroAgent sau Support) îi aparține."""

from pydantic import BaseModel, Field

from app.services.intent_router import AgentName


class ClassifyRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    # Implicit True — clasificarea primului mesaj al unei conversații NOI
    # poate folosi fallback-ul LLM (vezi intent_router.py), care n-are
    # niciun context anterior de unde să greșească. False pentru un mesaj
    # care CONTINUĂ o conversație deja angajată cu un agent — acolo un
    # fallback LLM STATELESS (fără istoricul conversației) ar clasifica
    # greșit un follow-up ambiguu ("Ce buffer?", fără niciun cuvânt-cheie
    # de buget) ca fiind Support, deși ține clar de continuarea discuției
    # cu MaestroAgent — bug real, raportat de user. Cu False, doar calea
    # rapidă (cuvinte-cheie) poate declanșa o schimbare de agent; restul
    # rămâne pe agentul deja angajat (vezi support.ts::askAgent).
    allow_llm_fallback: bool = True


class ClassifyResponse(BaseModel):
    agent: AgentName
    route: str
