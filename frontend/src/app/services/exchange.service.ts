import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../core/api-config';

export interface ExchangeRate {
  currency: string;
  mid_rate: number;
  spread_percent: number;
  commission_minor: number;
  is_demo: boolean;
}

export interface ExchangeQuote {
  from_currency: string;
  to_currency: string;
  amount_minor: number;
  received_minor: number;
  mid_rate: number;
  spread_percent: number;
  applied_rate: number;
  commission_minor: number;
  total_cost_minor: number;
  total_cost_percent: number;
  is_demo: boolean;
  generated_at: string;
}

export interface DemoExchangeReceipt {
  id: string;
  from_currency: string;
  to_currency: string;
  amount_minor: number;
  received_minor: number;
  applied_rate: number;
  commission_minor: number;
  total_cost_minor: number;
  is_demo: boolean;
  note: string;
  created_at: string;
}

/**
 * exchange-service — motor de schimb valutar DEMO (prin /api/exchange/*).
 * ⚠️ NU e o integrare FX reală — vezi backend/services/exchange-service/app/config.py.
 */
@Injectable({ providedIn: 'root' })
export class ExchangeService {
  constructor(private readonly http: HttpClient) {}

  getRates(): Observable<ExchangeRate[]> {
    return this.http.get<ExchangeRate[]>(`${API_BASE_URL}/exchange/rates`);
  }

  getQuote(fromCurrency: string, toCurrency: string, amountMinor: number): Observable<ExchangeQuote> {
    return this.http.get<ExchangeQuote>(`${API_BASE_URL}/exchange/quote`, {
      params: { from_currency: fromCurrency, to_currency: toCurrency, amount_minor: amountMinor },
    });
  }

  confirmDemoExchange(fromCurrency: string, toCurrency: string, amountMinor: number): Observable<DemoExchangeReceipt> {
    return this.http.post<DemoExchangeReceipt>(`${API_BASE_URL}/exchange/demo`, {
      from_currency: fromCurrency,
      to_currency: toCurrency,
      amount_minor: amountMinor,
    });
  }
}
