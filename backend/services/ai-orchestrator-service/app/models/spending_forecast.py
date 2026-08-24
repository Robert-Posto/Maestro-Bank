"""DTO-uri pentru Spending + Forecast Agent — vezi task-ul, secțiunea 11.
Toate sumele sunt în bani/subunități (`*_minor`), niciodată float — la fel
ca peste tot în restul backend-ului MaestroBank (nu formatăm bani aici,
frontend-ul o face prin MoneyPipe).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatHistoryMessage(BaseModel):
    """Un mesaj anterior din aceeași conversație — vezi task-ul, secțiunea
    18: "poți păstra doar un context foarte scurt al conversației dacă e
    necesar" (NU vector DB/memorie pe termen lung, doar istoricul turelor
    recente, trimis de frontend cu fiecare cerere). Serviciul NU persistă
    nimic — e stateless între cereri HTTP, dar conversația rămâne coerentă
    cât timp frontend-ul retrimite istoricul.
    """

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    # Limitat și aici (nu doar server-side în agent) — vezi
    # app/agents/spending_forecast.py::_MAX_HISTORY_MESSAGES pentru
    # trunchierea finală, defensivă indiferent ce trimite frontend-ul.
    history: list[ChatHistoryMessage] = Field(default_factory=list, max_length=40)


class Analysis(BaseModel):
    current_balance_minor: int
    recommended_buffer_minor: int


class RecurringPayments(BaseModel):
    # Numele `total_remaining_minor` vine exact din specificația primită —
    # reprezintă TOATE abonamentele active ale lunii curente (nu doar cele
    # nescadente încă). Vezi app/services/forecast_service.py::split_recurring_payments.
    total_remaining_minor: int
    already_paid_minor: int
    remaining_minor: int


class EstimatedExpenses(BaseModel):
    variable_minor: int
    discretionary_minor: int
    total_minor: int


class FinancialSummary(BaseModel):
    current_balance_minor: int
    # None dacă nu avem suficient istoric de încasări (vezi
    # forecast_service::estimate_remaining_income_minor) — o estimare din
    # ritmul recent de încasări, NU un forecast real de salariu.
    remaining_income_minor: int | None
    projected_expenses_minor: int
    estimated_end_balance_minor: int


class Metadata(BaseModel):
    agent: str = "spending_forecast"
    forecast_method: str = "deterministic"
    currency: str = "RON"


class KnowledgeSource(BaseModel):
    source: str
    score: float


class BudgetStatus(BaseModel):
    """Vezi app/services/budget_service.py::compute_budget_status."""

    id: str
    name: str
    category: str
    limit_minor: int
    spent_minor: int
    remaining_minor: int
    percent_used: float
    over_budget: bool


class PendingAction(BaseModel):
    """O acțiune PROPUSĂ de agent (creare/modificare/ștergere buget), NU
    încă executată — vezi app/services/budget_actions_service.py. Userul
    trebuie să confirme explicit din UI (buton), care apelează
    POST /spending-forecast/actions/confirm cu ACEST `type` + `payload`.
    """

    type: Literal["create_budget", "update_budget", "delete_budget"]
    summary: str
    payload: dict[str, Any]


class SpendingForecastResponse(BaseModel):
    answer: str
    affordable: bool | None = None
    requested_amount_minor: int | None = None

    analysis: Analysis
    recurring_payments: RecurringPayments
    estimated_expenses: EstimatedExpenses
    financial_summary: FinancialSummary

    recommendation: str

    # Cardurile din `analysis`/`recurring_payments`/`estimated_expenses`/
    # `financial_summary` pe care frontend-ul chiar trebuie să le arate
    # pentru ACEST răspuns — datele alea 4 secțiuni sunt mereu calculate
    # (mai jos, niciodată None), dar nu mereu relevante pentru întrebare
    # (vezi app/agents/spending_forecast.py::_relevant_cards). Poate fi
    # goală (ex. întrebare conceptuală, fără date de cont implicate).
    relevant_cards: list[str] = Field(default_factory=list)

    # Populate DOAR dacă GPT a ales tool-ul corespunzător pentru întrebare
    # (vezi app/tools/registry.py) — nu la fiecare răspuns.
    budgets: list[BudgetStatus] | None = None
    pending_action: PendingAction | None = None

    metadata: Metadata = Field(default_factory=Metadata)
    knowledge_used: list[KnowledgeSource] = Field(default_factory=list)


class ConfirmActionRequest(BaseModel):
    type: Literal["create_budget", "update_budget", "delete_budget"]
    payload: dict[str, Any]


class ConfirmActionResponse(BaseModel):
    success: bool
    message: str
    budget: dict[str, Any] | None = None
