"""DTO-uri pentru orchestrator-ul subțire — vezi app/routers/assistant.py.
NU e un al treilea agent — doar clasifică o întrebare NOUĂ și spune
frontend-ului cărei pagini (MaestroAgent sau Support) îi aparține."""

from pydantic import BaseModel, Field

from app.services.intent_router import AgentName


class ClassifyRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    # None — prima întrebare a unei conversații NOI, fără context anterior.
    # Setat — un mesaj care CONTINUĂ o conversație deja angajată cu acest
    # agent: vezi intent_router.py::classify_intent pentru cum schimbă asta
    # decizia (LLM-ul rămâne activ, dar primește agentul curent + istoric,
    # nu se oprește complet — asta era bug-ul reparat inițial prin oprirea
    # completă a LLM-ului, care bloca și schimbările reale de subiect fără
    # cuvânt-cheie exact).
    current_agent: AgentName | None = None
    # Ultimele câteva replici ale conversației (text simplu, "Client: ..."/
    # "Agent: ..."), folosite DOAR când current_agent e setat, ca LLM-ul să
    # aibă destul context să judece o continuare vs. o schimbare de subiect.
    # Limită mică — doar context, nu istoric complet (deja disponibil,
    # separat, în conversația persistată a fiecărui agent).
    recent_history: list[str] = Field(default_factory=list, max_length=6)


class ClassifyResponse(BaseModel):
    agent: AgentName
    route: str
