import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../core/api-config';

export interface SystemHealth {
  status: string;
  mongodb: string;
  services: Record<string, string>;
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  constructor(private readonly http: HttpClient) {}

  /** Status agregat: Gateway + MongoDB + fiecare microserviciu. */
  getSystemHealth(): Observable<SystemHealth> {
    return this.http.get<SystemHealth>(`${API_BASE_URL}/system/health`);
  }
}
