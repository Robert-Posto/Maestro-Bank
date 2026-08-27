import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../core/api-config';

export interface InstrumentView {
  symbol: string;
  name: string;
  price_minor: number | null;
  updated_at: string | null;
}

export interface HoldingView {
  symbol: string;
  name: string;
  quantity: number;
  avg_cost_minor_per_share: number;
  current_price_minor: number;
  current_value_minor: number;
  unrealized_gain_minor: number;
  unrealized_gain_percent: number;
}

/**
 * investments-service — cumpărare/vânzare de acțiuni/ETF-uri (catalog
 * curatoriat, 16 simboluri, prin /api/investments/*). Prețul e REAL, dar
 * dintr-un endpoint NEOFICIAL Yahoo Finance (nu există echivalent gratuit,
 * fără cheie, oficial, pentru cotații bursiere live — spre deosebire de
 * BNR la Schimb valutar) — vezi backend/services/investments-service/app/prices.py.
 * Execuția chiar mută solduri, prin accounts-service. Necesită ca userul
 * să aibă deja deschis contul USD (toate instrumentele se tranzacționează
 * în USD) — altfel backend-ul întoarce 400.
 */
@Injectable({ providedIn: 'root' })
export class InvestmentsService {
  constructor(private readonly http: HttpClient) {}

  listInstruments(): Observable<InstrumentView[]> {
    return this.http.get<InstrumentView[]>(`${API_BASE_URL}/investments/instruments`);
  }

  getPortfolio(): Observable<HoldingView[]> {
    return this.http.get<HoldingView[]>(`${API_BASE_URL}/investments/portfolio`);
  }

  buy(symbol: string, amountMinor: number): Observable<HoldingView> {
    return this.http.post<HoldingView>(`${API_BASE_URL}/investments/buy`, { symbol, amount_minor: amountMinor });
  }

  sell(symbol: string, quantity: number): Observable<HoldingView> {
    return this.http.post<HoldingView>(`${API_BASE_URL}/investments/sell`, { symbol, quantity });
  }
}
