import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../core/api-config';
import { TransactionView } from './banking.service';

export interface TransactionFilters {
  search?: string;
  direction?: 'incoming' | 'outgoing';
  category?: string;
  date_from?: string;
  date_to?: string;
  min_amount_minor?: number;
  max_amount_minor?: number;
  account_id?: string;
}

export interface SpendingByCategory {
  category: string;
  amount_minor: number;
  percentage: number;
}

export interface SpendingAnalytics {
  month: string;
  total_spent_minor: number;
  average_daily_spending_minor: number;
  by_category: SpendingByCategory[];
}

export interface CashFlowPoint {
  date: string;
  incoming_minor: number;
  outgoing_minor: number;
  net_minor: number;
}

export interface CashFlowAnalytics {
  period_days: number;
  points: CashFlowPoint[];
}

export interface UpcomingObligation {
  name: string;
  amount_minor: number;
  billing_day: number;
}

export interface ForecastAnalytics {
  current_balance_minor: number;
  expected_expenses_minor: number;
  upcoming_obligations: UpcomingObligation[];
  estimated_end_of_month_balance_minor: number;
  days_remaining_in_month: number;
}

/**
 * Tot ce ține de /api/transactions (dincolo de listarea/transferul de
 * bază, deja acoperite de BankingService): filtre, export CSV, analytics
 * (Spending & Forecast), recognize/report.
 */
@Injectable({ providedIn: 'root' })
export class TransactionsService {
  constructor(private readonly http: HttpClient) {}

  private buildParams(filters: TransactionFilters, extra: Record<string, string | number> = {}): HttpParams {
    let params = new HttpParams();
    for (const [key, value] of Object.entries({ ...filters, ...extra })) {
      if (value !== undefined && value !== null && value !== '') {
        params = params.set(key, String(value));
      }
    }
    return params;
  }

  list(filters: TransactionFilters, limit = 20, skip = 0): Observable<TransactionView[]> {
    const params = this.buildParams(filters, { limit, skip });
    return this.http.get<TransactionView[]>(`${API_BASE_URL}/transactions`, { params });
  }

  getById(id: string): Observable<TransactionView> {
    return this.http.get<TransactionView>(`${API_BASE_URL}/transactions/${id}`);
  }

  recognize(id: string): Observable<TransactionView> {
    return this.http.patch<TransactionView>(`${API_BASE_URL}/transactions/${id}/recognize`, {});
  }

  report(id: string, reason = ''): Observable<TransactionView> {
    return this.http.post<TransactionView>(`${API_BASE_URL}/transactions/${id}/report`, { reason });
  }

  /** Doar pentru tranzacții proprii, încă "pending_review" — vezi app/holds.py::cancel_hold din backend. */
  cancelHold(id: string): Observable<TransactionView> {
    return this.http.post<TransactionView>(`${API_BASE_URL}/transactions/${id}/hold/cancel`, {});
  }

  exportCsv(filters: TransactionFilters): Observable<Blob> {
    const params = this.buildParams(filters);
    return this.http.get(`${API_BASE_URL}/transactions/export`, { params, responseType: 'blob' });
  }

  /** Extras de cont (PDF) — spre deosebire de exportCsv, perioada e
   * OBLIGATORIE (vezi backend GET /transactions/statement); `dateFrom`/
   * `dateTo` sunt ISO datetime strings complete (nu doar "yyyy-MM-dd").
   * `accountId` OPȚIONAL — implicit contul curent (ca până acum), sau
   * orice alt cont al userului (vezi pagina Conturi). */
  downloadStatement(dateFrom: string, dateTo: string, accountId?: string): Observable<Blob> {
    let params = new HttpParams().set('date_from', dateFrom).set('date_to', dateTo);
    if (accountId) params = params.set('account_id', accountId);
    return this.http.get(`${API_BASE_URL}/transactions/statement`, { params, responseType: 'blob' });
  }

  getSpendingAnalytics(): Observable<SpendingAnalytics> {
    return this.http.get<SpendingAnalytics>(`${API_BASE_URL}/transactions/analytics/spending`);
  }

  getCashFlowAnalytics(days = 30): Observable<CashFlowAnalytics> {
    return this.http.get<CashFlowAnalytics>(`${API_BASE_URL}/transactions/analytics/cash-flow?days=${days}`);
  }

  getForecastAnalytics(): Observable<ForecastAnalytics> {
    return this.http.get<ForecastAnalytics>(`${API_BASE_URL}/transactions/analytics/forecast`);
  }
}
