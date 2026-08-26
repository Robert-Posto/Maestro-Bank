import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../core/api-config';
import { AccountView, TransactionView } from './banking.service';

/**
 * Tot ce ține de /api/transactions/staff — accesibil DOAR unui JWT cu
 * role="staff" (vezi backend transactions-service/app/security.py
 * ::require_staff). Rutele oricum verifică rolul server-side; ghidul de
 * UI (staffGuard) există doar ca să nu arate un ecran gol/eroare unui
 * client obișnuit care ar naviga direct la /admin/holds.
 */

export interface StaffHoldCustomerContact {
  first_name: string;
  last_name: string;
  email: string;
  phone_number: string | null;
}

export interface StaffHoldView {
  id: string;
  user_id: string | null;
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
  /** Analiza AI (Financial Guardian) în limbaj natural, DOAR pentru
   * personal — vezi backend app/guardian/. Poate fi null pe scurt timp,
   * imediat după crearea reținerii, cât timp analiza încă se generează. */
  guardian_staff_explanation: string | null;
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

export interface GuardianEvaluationView {
  status: 'ready' | 'template_fallback';
  staff_explanation: string | null;
  customer_tier: string | null;
  customer_phrase: string | null;
  source: 'llm' | 'template' | null;
  generated_at: string | null;
  model: string | null;
}

export interface BlocklistEntryView {
  id: string;
  iban: string;
  added_by: string;
  reason: string;
  source: 'confirmed_fraud_review' | 'manual';
  evaluation_id: string | null;
  created_at: string;
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
  guardian: GuardianEvaluationView | null;
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

  /** READ-ONLY — contul/istoricul unui client oarecare, pentru revizuirea
   * unei rețineri (vezi accounts-service și transactions-service,
   * routers/staff.py::get_customer_accounts / get_customer_transactions).
   * Niciun endpoint de scriere aici — personalul nu poate face transferuri
   * sau modifica nimic din contul clientului, doar vede. */
  getCustomerAccounts(userId: string): Observable<AccountView[]> {
    return this.http.get<AccountView[]>(`${API_BASE_URL}/accounts/staff/customers/${userId}/accounts`);
  }

  getCustomerTransactions(userId: string, limit = 20, skip = 0): Observable<TransactionView[]> {
    return this.http.get<TransactionView[]>(
      `${API_BASE_URL}/transactions/staff/customers/${userId}/transactions?limit=${limit}&skip=${skip}`,
    );
  }

  /** Beneficiari refuzați direct, înainte de scoring — vezi BEN-04 (backend
   * app/blocklist.py). Scriere DOAR de personal — niciodată dintr-un raport
   * de fraudă al unui client. */
  listBlocklist(): Observable<BlocklistEntryView[]> {
    return this.http.get<BlocklistEntryView[]>(`${API_BASE_URL}/transactions/staff/blocklist`);
  }

  addToBlocklist(iban: string, reason: string): Observable<BlocklistEntryView> {
    return this.http.post<BlocklistEntryView>(`${API_BASE_URL}/transactions/staff/blocklist`, { iban, reason });
  }

  removeFromBlocklist(entryId: string): Observable<void> {
    return this.http.delete<void>(`${API_BASE_URL}/transactions/staff/blocklist/${entryId}`);
  }
}
