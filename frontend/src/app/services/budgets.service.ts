import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../core/api-config';

export type BudgetPeriod = 'weekly' | 'monthly' | 'yearly';

export interface Budget {
  id: string;
  name: string;
  category: string;
  limit_minor: number;
  period: BudgetPeriod;
  active: boolean;
  created_at: string;
}

export interface BudgetPayload {
  name: string;
  category: string;
  limit_minor: number;
  period: BudgetPeriod;
}

export interface Subscription {
  id: string;
  name: string;
  amount_minor: number;
  currency: string;
  billing_day: number;
  category: string;
  active: boolean;
  created_at: string;
}

export interface SubscriptionPayload {
  name: string;
  amount_minor: number;
  billing_day: number;
  currency?: string;
  category?: string;
}

/** Bugete + abonamente (budgets-service, prin /api/budgets/*). */
@Injectable({ providedIn: 'root' })
export class BudgetsService {
  constructor(private readonly http: HttpClient) {}

  // --- Budgets ---------------------------------------------------------

  listBudgets(): Observable<Budget[]> {
    return this.http.get<Budget[]>(`${API_BASE_URL}/budgets/budgets`);
  }

  createBudget(payload: BudgetPayload): Observable<Budget> {
    return this.http.post<Budget>(`${API_BASE_URL}/budgets/budgets`, payload);
  }

  updateBudget(id: string, payload: Partial<BudgetPayload & { active: boolean }>): Observable<Budget> {
    return this.http.patch<Budget>(`${API_BASE_URL}/budgets/budgets/${id}`, payload);
  }

  deleteBudget(id: string): Observable<void> {
    return this.http.delete<void>(`${API_BASE_URL}/budgets/budgets/${id}`);
  }

  // --- Subscriptions -----------------------------------------------------

  listSubscriptions(): Observable<Subscription[]> {
    return this.http.get<Subscription[]>(`${API_BASE_URL}/budgets/subscriptions`);
  }

  createSubscription(payload: SubscriptionPayload): Observable<Subscription> {
    return this.http.post<Subscription>(`${API_BASE_URL}/budgets/subscriptions`, payload);
  }

  updateSubscription(id: string, payload: Partial<SubscriptionPayload & { active: boolean }>): Observable<Subscription> {
    return this.http.patch<Subscription>(`${API_BASE_URL}/budgets/subscriptions/${id}`, payload);
  }

  deleteSubscription(id: string): Observable<void> {
    return this.http.delete<void>(`${API_BASE_URL}/budgets/subscriptions/${id}`);
  }
}
