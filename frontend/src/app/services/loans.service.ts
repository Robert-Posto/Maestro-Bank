import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../core/api-config';

export type LoanTermMonths = 12 | 24 | 36 | 60;
export type LoanStatus = 'active' | 'paid_off';

export interface LoanRateView {
  term_months: LoanTermMonths;
  rate_percent_annual: number;
}

export interface LoanView {
  id: string;
  principal_minor: number;
  outstanding_principal_minor: number;
  term_months: LoanTermMonths;
  rate_percent_annual: number;
  monthly_installment_minor: number;
  payments_made: number;
  opened_at: string;
  next_payment_due_at: string | null;
  status: LoanStatus;
  paid_off_at: string | null;
}

export interface LoanPaymentView {
  id: string;
  loan_id: string;
  paid_at: string;
  amount_minor: number;
  interest_portion_minor: number;
  principal_portion_minor: number;
  outstanding_after_minor: number;
}

/**
 * loans-service — credite personale, execuție reală prin accounts-service.
 * Dobânda anuală e o politică proprie MaestroBank (ca la Depozite, vezi
 * backend/services/loans-service/app/rates.py) — rata lunară se calculează
 * cu formula standard de amortizare. Aprobarea verifică REAL eligibilitatea
 * (venitul mediu din istoricul de tranzacții, vezi app/eligibility.py) —
 * o cerere poate fi respinsă (422), cu motivul exact în `detail`. Rata se
 * plătește AUTOMAT lunar; plata anticipată (`payoff`) achită doar restul de
 * principal.
 */
@Injectable({ providedIn: 'root' })
export class LoansService {
  constructor(private readonly http: HttpClient) {}

  getRates(): Observable<LoanRateView[]> {
    return this.http.get<LoanRateView[]>(`${API_BASE_URL}/loans/rates`);
  }

  listMine(): Observable<LoanView[]> {
    return this.http.get<LoanView[]>(`${API_BASE_URL}/loans`);
  }

  apply(amountMinor: number, termMonths: LoanTermMonths): Observable<LoanView> {
    return this.http.post<LoanView>(`${API_BASE_URL}/loans/apply`, { amount_minor: amountMinor, term_months: termMonths });
  }

  getPayments(loanId: string): Observable<LoanPaymentView[]> {
    return this.http.get<LoanPaymentView[]>(`${API_BASE_URL}/loans/${loanId}/payments`);
  }

  payoff(loanId: string): Observable<LoanView> {
    return this.http.post<LoanView>(`${API_BASE_URL}/loans/${loanId}/payoff`, {});
  }
}
