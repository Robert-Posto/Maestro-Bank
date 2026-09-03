"""DTO-uri Pydantic pentru Support Agent.

Extern (prin Gateway): POST /api/ai/support — input `ChatRequest`, output
`ChatResponse`. Vezi app/services/support_service.py pentru fluxul de
confirmare (requires_confirmation / pending_action) al acțiunilor de scriere.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

Intent = Literal[
    "account_help",
    "card_status",
    "card_help",
    "transaction_details",
    "transaction_not_recognized",
    "transfer_status",
    "navigation_help",
    "support_ticket",
    "unknown",
]

TicketCategory = Literal["card", "transfer", "account", "technical", "other"]


class ChatMessage(BaseModel):
    """O tură anterioară de conversație. Serviciul e stateless (fără
    sesiune persistentă) — callerul (frontend) e responsabil să retrimită
    istoricul relevant la fiecare request, exact ca la orice chat API
    request-response normal."""

    role: Literal["user", "assistant"]
    content: str


class PendingAction(BaseModel):
    """Acțiune de SCRIERE propusă de agent, NEEXECUTATĂ încă. Callerul o
    retrimite neschimbată, ca `pending_action`, în request-ul următor, în
    care userul confirmă explicit — vezi app/services/support_service.py."""

    tool: Literal[
        "create_support_ticket",
        "propose_internal_transfer",
        "propose_update_card_settings",
        "propose_open_account",
        "propose_execute_exchange",
    ]
    arguments: dict[str, Any]


class RecommendedAction(BaseModel):
    type: str
    label: str
    # Rută REALĂ Angular (ex. "/app/cards"), rezolvată determinist de
    # backend din `type` (vezi app/services/support_service.py::_ACTION_ROUTES)
    # — NU generată/inventată de GPT, care alege doar `type`+`label`. None
    # pentru acțiunile care nu navighează nicăieri (ex. "view_tickets"),
    # caz în care frontend-ul retrimite `label` ca mesaj nou.
    route: str | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    # Limitat și aici (nu doar server-side în agent, vezi
    # app/agents/support.py::_MAX_HISTORY_MESSAGES) — evită context
    # nemărginit (cost/latență) indiferent ce trimite clientul. Acum că
    # frontend-ul persistă conversația (sessionStorage), istoricul poate
    # deveni lung în timp — mai important ca oricând să fie plafonat.
    # Populat de router DIN Mongo (vezi conversation_service.to_history_dicts),
    # NU de client — clientul trimite conversation_id în loc (mai jos).
    # Rămâne aici (nu doar parametru de funcție, ca la spending_forecast)
    # pentru că support_service.handle_chat citește payload.history direct.
    history: list[ChatMessage] = Field(default_factory=list, max_length=40)
    pending_action: PendingAction | None = None
    # None = pornește o conversație nouă (titlu din acest mesaj).
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    intent: Intent
    context: dict[str, Any] = Field(default_factory=dict)
    recommended_actions: list[RecommendedAction] = Field(default_factory=list)
    requires_confirmation: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Setat de router DUPĂ ce support_service.handle_chat întoarce — niciodată
    # de handle_chat însuși.
    conversation_id: str = ""
