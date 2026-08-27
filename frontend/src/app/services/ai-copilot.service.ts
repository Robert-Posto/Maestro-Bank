import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../core/api-config';

/**
 * Shape-uri identice cu DTO-ul întors de ai-orchestrator-service — vezi
 * backend/services/ai-orchestrator-service/app/models/spending_forecast.py.
 * Toate sumele sunt în bani/subunități (*_minor), formatate prin MoneyPipe
 * în template, niciodată aici.
 */
export interface SpendingForecastAnalysis {
  current_balance_minor: number;
  recommended_buffer_minor: number;
}

export interface SpendingForecastRecurringPayments {
  total_remaining_minor: number;
  already_paid_minor: number;
  remaining_minor: number;
}

export interface SpendingForecastEstimatedExpenses {
  variable_minor: number;
  discretionary_minor: number;
  total_minor: number;
}

export interface SpendingForecastFinancialSummary {
  current_balance_minor: number;
  remaining_income_minor: number | null;
  projected_expenses_minor: number;
  estimated_end_balance_minor: number;
}

export interface SpendingForecastKnowledgeSource {
  source: string;
  score: number;
}

export interface BudgetStatus {
  id: string;
  name: string;
  category: string;
  limit_minor: number;
  spent_minor: number;
  remaining_minor: number;
  percent_used: number;
  over_budget: boolean;
}

/**
 * O acțiune de buget PROPUSĂ de agent (creare/modificare/ștergere), NU
 * încă executată — userul trebuie să apese explicit "Confirmă" (vezi
 * copilot.ts::confirmPendingAction). `payload` e opac pentru frontend,
 * se trimite mai departe neschimbat la /actions/confirm.
 */
export interface PendingAction {
  type: 'create_budget' | 'update_budget' | 'delete_budget';
  summary: string;
  payload: Record<string, unknown>;
}

export interface SpendingForecastResponse {
  answer: string;
  affordable: boolean | null;
  requested_amount_minor: number | null;
  conversation_id: string;
  analysis: SpendingForecastAnalysis;
  recurring_payments: SpendingForecastRecurringPayments;
  estimated_expenses: SpendingForecastEstimatedExpenses;
  financial_summary: SpendingForecastFinancialSummary;
  recommendation: string;
  /** Care dintre cardurile analysis/recurring_payments/estimated_expenses/
   * financial_summary sunt relevante pentru ACEST răspuns — datele sunt
   * mereu calculate, dar afișăm doar cardurile care chiar răspund la
   * întrebare (vezi copilot.html). Poate fi goală. */
  relevant_cards: string[];
  budgets: BudgetStatus[] | null;
  pending_action: PendingAction | null;
  metadata: { agent: string; forecast_method: string; currency: string };
  knowledge_used: SpendingForecastKnowledgeSource[];
}

export interface ConfirmActionResponse {
  success: boolean;
  message: string;
  budget: Record<string, unknown> | null;
}

export interface ConversationSummary {
  id: string;
  title: string;
  updated_at: string;
}

export interface ConversationMessage {
  role: 'user' | 'assistant';
  content: string;
  response: SpendingForecastResponse | null;
  created_at: string;
}

export interface ConversationDetail {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: ConversationMessage[];
}

/**
 * Client pentru agentul Spending + Forecast (ai-orchestrator-service, prin
 * Gateway) — vezi backend/services/ai-orchestrator-service. Un răspuns
 * implică 1+ apeluri GPT (tool-calling), deci poate dura 10-20s — vezi
 * copilot.ts pentru starea de "se gândește" din UI cât timp așteptăm.
 */
@Injectable({ providedIn: 'root' })
export class AiCopilotService {
  constructor(private readonly http: HttpClient) {}

  sendMessage(message: string, conversationId: string | null): Observable<SpendingForecastResponse> {
    return this.http.post<SpendingForecastResponse>(`${API_BASE_URL}/ai/spending-forecast/chat`, {
      message,
      conversation_id: conversationId,
    });
  }

  listConversations(): Observable<ConversationSummary[]> {
    return this.http.get<ConversationSummary[]>(`${API_BASE_URL}/ai/spending-forecast/conversations`);
  }

  getConversation(id: string): Observable<ConversationDetail> {
    return this.http.get<ConversationDetail>(`${API_BASE_URL}/ai/spending-forecast/conversations/${id}`);
  }

  deleteConversation(id: string): Observable<void> {
    return this.http.delete<void>(`${API_BASE_URL}/ai/spending-forecast/conversations/${id}`);
  }

  /** Execută REAL o acțiune de buget propusă anterior — apelată STRICT
   * după ce userul apasă "Confirmă". NU trece prin GPT. */
  confirmAction(action: PendingAction): Observable<ConfirmActionResponse> {
    return this.http.post<ConfirmActionResponse>(`${API_BASE_URL}/ai/spending-forecast/actions/confirm`, {
      type: action.type,
      payload: action.payload,
    });
  }
}
