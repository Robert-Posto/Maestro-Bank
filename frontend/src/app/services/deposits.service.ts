import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../core/api-config';

export type DepositCurrency = 'RON' | 'EUR' | 'USD' | 'GBP';
export type DepositTermMonths = 3 | 6 | 12 | 24;
export type DepositStatus = 'active' | 'matured_renewed' | 'liquidated_early' | 'closed_paid_out';

export interface DepositRateView {
  currency: DepositCurrency;
  term_months: DepositTermMonths;
  rate_percent_annual: number;
}

export interface DepositView {
  id: string;
  currency: DepositCurrency;
  principal_minor: number;
  term_months: DepositTermMonths;
  rate_percent_annual: number;
  interest_minor: number;
  opened_at: string;
  matures_at: string;
  renew_at_maturity: boolean;
  status: DepositStatus;
  renewed_into_deposit_id: string | null;
  renewed_from_deposit_id: string | null;
}

/**
 * deposits-service — depozite la termen (prin /api/deposits/*). Rata e
 * politică proprie MaestroBank (NU un feed extern, spre deosebire de
 * exchange-service) — vezi backend/services/deposits-service/app/rates.py.
 * Execuția (deschidere/lichidare) chiar mută solduri, prin accounts-service.
 * Necesită ca userul să aibă deja deschis contul pe moneda aleasă (current
 * pt RON, eur/usd/gbp altfel) — altfel backend-ul întoarce 400.
 */
@Injectable({ providedIn: 'root' })
export class DepositsService {
  constructor(private readonly http: HttpClient) {}

  listRates(): Observable<DepositRateView[]> {
    return this.http.get<DepositRateView[]>(`${API_BASE_URL}/deposits/rates`);
  }

  listMine(): Observable<DepositView[]> {
    return this.http.get<DepositView[]>(`${API_BASE_URL}/deposits`);
  }

  open(
    currency: DepositCurrency,
    termMonths: DepositTermMonths,
    amountMinor: number,
    renewAtMaturity: boolean,
  ): Observable<DepositView> {
    return this.http.post<DepositView>(`${API_BASE_URL}/deposits`, {
      currency,
      term_months: termMonths,
      amount_minor: amountMinor,
      renew_at_maturity: renewAtMaturity,
    });
  }

  liquidate(id: string): Observable<DepositView> {
    return this.http.post<DepositView>(`${API_BASE_URL}/deposits/${id}/liquidate`, {});
  }
}
