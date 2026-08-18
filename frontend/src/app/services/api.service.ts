import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../core/api-config';

export interface SystemHealth {
  status: string;
  mongodb: string;
  services: Record<string, string>;
}

export interface TestItem {
  id: string;
  name: string;
}

export interface TestItemCreate {
  name: string;
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  constructor(private readonly http: HttpClient) {}

  /** Status agregat: Gateway + MongoDB + fiecare microserviciu. */
  getSystemHealth(): Observable<SystemHealth> {
    return this.http.get<SystemHealth>(`${API_BASE_URL}/system/health`);
  }

  /**
   * @deprecated DEVELOPMENT-ONLY — au fost utile pentru verificarea
   * inițială a arhitecturii (Angular -> Nginx -> Gateway ->
   * accounts-service -> accounts_db). Nu mai sunt afișate în UI-ul
   * principal (vezi Core Banking Test Panel); păstrate doar pentru
   * debugging manual. Nu construi funcționalități noi peste ele.
   */
  getTestItems(): Observable<TestItem[]> {
    return this.http.get<TestItem[]>(`${API_BASE_URL}/accounts/test-items`);
  }

  /** @deprecated DEVELOPMENT-ONLY — vezi getTestItems(). */
  createTestItem(item: TestItemCreate): Observable<TestItem> {
    return this.http.post<TestItem>(`${API_BASE_URL}/accounts/test-items`, item);
  }
}
