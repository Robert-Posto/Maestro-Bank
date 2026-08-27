import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../core/api-config';

export interface InstrumentView {
  symbol: string;
  name: string;
  price_minor: number | null;
  previous_close_minor: number | null;
  change_percent: number | null;
  updated_at: string | null;
}

export interface HistoryPointView {
  date: string;
  price_minor: number;
}

export interface InstrumentDetailView {
  symbol: string;
  name: string;
  is_tradable: boolean;
  price_minor: number;
  previous_close_minor: number;
  change_percent: number | null;
  day_high_minor: number;
  day_low_minor: number;
  week52_high_minor: number;
  week52_low_minor: number;
  volume: number | null;
  history: HistoryPointView[];
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
 * curatoriat, 16 simboluri, prin /api/investments/*), plus indici bursieri
 * reali (informativi, NU tranzacționabili — vezi backend/services/
 * investments-service/app/catalog.py::INDICES). Prețul e REAL, dar dintr-un
 * endpoint NEOFICIAL Yahoo Finance (nu există echivalent gratuit, fără
 * cheie, oficial, pentru cotații bursiere live — spre deosebire de BNR la
 * Schimb valutar) — vezi backend/services/investments-service/app/prices.py.
 * Execuția (cumpărare/vânzare) chiar mută solduri, prin accounts-service.
 * Necesită ca userul să aibă deja deschis contul USD (toate instrumentele
 * se tranzacționează în USD) — altfel backend-ul întoarce 400.
 */
@Injectable({ providedIn: 'root' })
export class InvestmentsService {
  constructor(private readonly http: HttpClient) {}

  listInstruments(): Observable<InstrumentView[]> {
    return this.http.get<InstrumentView[]>(`${API_BASE_URL}/investments/instruments`);
  }

  listIndices(): Observable<InstrumentView[]> {
    return this.http.get<InstrumentView[]>(`${API_BASE_URL}/investments/indices`);
  }

  getDetail(symbol: string): Observable<InstrumentDetailView> {
    return this.http.get<InstrumentDetailView>(`${API_BASE_URL}/investments/instruments/${symbol}/detail`);
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
