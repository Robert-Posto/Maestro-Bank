import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../core/api-config';

/**
 * Tot ce ține de /api/transactions/staff — accesibil DOAR unui JWT cu
 * role="staff" (vezi backend transactions-service/app/security.py
 * ::require_staff). Rutele oricum verifică rolul server-side; ghidul de
 * UI (staffGuard) există doar ca să nu arate un ecran gol/eroare unui
 * client obișnuit care ar naviga direct la /app/staff-holds.
 */

export interface StaffHoldCustomerContact {
  first_name: string;
  last_name: string;
  email: string;
  phone_number: string | null;
}

export interface StaffHoldView {
  id: string;
  from_iban: string;
  to_iban: string;
  from_name: string | null;
  to_name: string | null;
  amount_minor: number;
  currency: string;
  description: string;
  category: string;
  status: string;
  created_at: string;
  hold_expires_at: string | null;
  score: number | null;
  fired_rule_ids: string[];
  customer: StaffHoldCustomerContact | null;
}

export interface HoldResolutionView {
  id: string;
  status: string;
  resolution: string | null;
}

export interface FraudEvaluationReview {
  reviewed_by: string;
  reviewed_at: string;
  outcome: 'confirmed_fraud' | 'false_positive' | 'legitimate';
  note: string;
}

export interface FraudEvaluationView {
  id: string;
  transaction_id: string;
  user_id: string;
  status: string;
  score: number | null;
  fired_rules: Record<string, unknown>[];
  decision_would_apply: string | null;
  ruleset_version: string;
  shadow_mode: boolean;
  evaluated_at: string;
  error: string | null;
  created_at: string;
  review: FraudEvaluationReview | null;
}

@Injectable({ providedIn: 'root' })
export class StaffService {
  constructor(private readonly http: HttpClient) {}

  listHolds(): Observable<StaffHoldView[]> {
    return this.http.get<StaffHoldView[]>(`${API_BASE_URL}/transactions/staff/holds`);
  }

  approveHold(transactionId: string): Observable<HoldResolutionView> {
    return this.http.post<HoldResolutionView>(`${API_BASE_URL}/transactions/staff/holds/${transactionId}/approve`, {});
  }

  rejectHold(transactionId: string): Observable<HoldResolutionView> {
    return this.http.post<HoldResolutionView>(`${API_BASE_URL}/transactions/staff/holds/${transactionId}/reject`, {});
  }

  listFraudEvaluations(params: { decisionBand?: string; reviewed?: boolean } = {}): Observable<FraudEvaluationView[]> {
    const query = new URLSearchParams();
    if (params.decisionBand) query.set('decision_band', params.decisionBand);
    if (params.reviewed !== undefined) query.set('reviewed', String(params.reviewed));
    const suffix = query.toString() ? `?${query.toString()}` : '';
    return this.http.get<FraudEvaluationView[]>(`${API_BASE_URL}/transactions/staff/fraud-evaluations${suffix}`);
  }
}
