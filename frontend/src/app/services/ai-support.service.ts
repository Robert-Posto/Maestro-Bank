import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../core/api-config';

export interface AiChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface AiPendingAction {
  tool: string;
  arguments: Record<string, unknown>;
}

export interface AiRecommendedAction {
  type: string;
  label: string;
  /** Rută REALĂ Angular (ex. "/app/cards"), rezolvată determinist de
   * backend (vezi app/services/support_service.py::_ACTION_ROUTES) — NU
   * generată de GPT. Absentă/null pentru acțiuni care NU navighează
   * nicăieri (ex. "view_tickets") — acolo frontend-ul retrimite `label`
   * ca mesaj nou, la fel ca o întrebare rapidă. */
  route?: string | null;
}

export interface AiChatRequest {
  message: string;
  history?: AiChatMessage[];
  pending_action?: AiPendingAction | null;
}

export interface AiChatResponse {
  answer: string;
  intent: string;
  context: Record<string, unknown>;
  recommended_actions: AiRecommendedAction[];
  requires_confirmation: boolean;
  metadata: Record<string, unknown>;
}

/** ai-orchestrator-service (Support Agent), prin /api/ai/support. */
@Injectable({ providedIn: 'root' })
export class AiSupportService {
  constructor(private readonly http: HttpClient) {}

  chat(payload: AiChatRequest): Observable<AiChatResponse> {
    return this.http.post<AiChatResponse>(`${API_BASE_URL}/ai/support`, payload);
  }
}
