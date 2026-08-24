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
