import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../core/api-config';

export interface AccountView {
  id: string;
  iban: string;
  currency: string;
  balance_minor: number;
  balance: string;
  status: string;
}

export interface CardView {
  id: string;
  user_id: string;
  account_id: string;
  last_four: string;
  expiry_month: number;
  expiry_year: number;
  status: string;
  type: string;
  created_at: string;
}

export interface TransactionView {
  id: string;
  direction: 'incoming' | 'outgoing';
  amount_minor: number;
  amount: string;
  currency: string;
  counterparty_iban: string;
  description: string;
  status: string;
  created_at: string;
}

export interface TransferPayload {
  to_iban: string;
  amount_minor: number;
  description: string;
}

@Injectable({ providedIn: 'root' })
export class BankingService {
  constructor(private readonly http: HttpClient) {}

  getMyAccount(): Observable<AccountView> {
    return this.http.get<AccountView>(`${API_BASE_URL}/accounts/me`);
  }

  getMyCards(): Observable<CardView[]> {
    return this.http.get<CardView[]>(`${API_BASE_URL}/accounts/me/cards`);
  }

  /** ⚠️ STRICT development-only — vezi backend accounts-service POST /accounts/dev/fund. */
  devFund(amountMinor: number): Observable<AccountView> {
    return this.http.post<AccountView>(`${API_BASE_URL}/accounts/dev/fund`, { amount_minor: amountMinor });
  }

  createTransfer(payload: TransferPayload): Observable<TransactionView> {
    return this.http.post<TransactionView>(`${API_BASE_URL}/transactions/transfers`, payload);
  }

  getTransactions(limit = 20, skip = 0): Observable<TransactionView[]> {
    return this.http.get<TransactionView[]>(`${API_BASE_URL}/transactions?limit=${limit}&skip=${skip}`);
  }
}
