import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../core/api-config';

export interface ClassifyResultView {
  agent: 'spending_forecast' | 'support';
  route: string;
}

/**
 * Orchestrator SUBȚIRE — clasifică o întrebare nouă (determinist, pe
 * cuvinte-cheie, vezi backend/services/ai-orchestrator-service/app/services/
 * intent_router.py) și spune cărei pagini îi aparține (MaestroAgent sau
 * Support), ca userul să nu mai aleagă manual. NU rulează el conversația —
 * doar clasifică o dată, la început; pagina țintă preia mesajul și
 * continuă exact ca și cum userul ar fi scris direct acolo.
 */
@Injectable({ providedIn: 'root' })
export class AssistantService {
  constructor(private readonly http: HttpClient) {}

  classify(message: string): Observable<ClassifyResultView> {
    return this.http.post<ClassifyResultView>(`${API_BASE_URL}/ai/assistant/classify`, { message });
  }
}
