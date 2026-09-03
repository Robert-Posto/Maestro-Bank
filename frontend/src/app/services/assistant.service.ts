import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../core/api-config';

export interface ClassifyResultView {
  agent: 'spending_forecast' | 'support';
  route: string;
}

/**
 * Orchestrator SUBȚIRE — clasifică o întrebare nouă (cuvinte-cheie +
 * fallback LLM pentru formulări fără cuvânt-cheie clar, vezi backend/
 * services/ai-orchestrator-service/app/services/intent_router.py) și spune
 * cărei pagini îi aparține (MaestroAgent sau Support), ca userul să nu mai
 * aleagă manual. NU rulează el conversația — doar clasifică; pagina țintă
 * preia mesajul și continuă exact ca și cum userul ar fi scris direct
 * acolo. Apelat la FIECARE mesaj nou din support.ts::askAgent (nu doar
 * primul al unei conversații), ca un schimb de subiect în mijlocul unei
 * conversații să redirecționeze automat, nu doar la pornirea uneia noi.
 */
@Injectable({ providedIn: 'root' })
export class AssistantService {
  constructor(private readonly http: HttpClient) {}

  /** `currentAgent` — `undefined` pentru prima întrebare a unei conversații
   * NOI (clasificare hibridă completă, fără context de unde să greșească).
   * Setat pentru un mesaj care CONTINUĂ o conversație deja angajată — vezi
   * support.ts::askAgent: backend-ul (intent_router.py) NU mai oprește
   * complet LLM-ul în cazul ăsta (asta bloca reclasificarea reală fără
   * cuvânt-cheie — bug raportat), ci îl consultă din nou, dar CU context
   * (`currentAgent` + `recentHistory`), ca să distingă o continuare
   * firească de o schimbare reală de subiect. */
  classify(message: string, currentAgent?: 'spending_forecast' | 'support', recentHistory: string[] = []): Observable<ClassifyResultView> {
    return this.http.post<ClassifyResultView>(`${API_BASE_URL}/ai/assistant/classify`, {
      message,
      current_agent: currentAgent ?? null,
      recent_history: recentHistory,
    });
  }
}
