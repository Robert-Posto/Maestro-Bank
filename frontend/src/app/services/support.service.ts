import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../core/api-config';

export type TicketCategory = 'card' | 'transfer' | 'account' | 'technical' | 'other';
export type TicketStatus = 'open' | 'in_progress' | 'resolved';

export interface SupportTicket {
  id: string;
  subject: string;
  category: TicketCategory;
  message: string;
  status: TicketStatus;
  created_at: string;
  updated_at: string;
}

export interface TicketPayload {
  subject: string;
  category: TicketCategory;
  message: string;
}

/** support-service, prin /api/support/tickets. */
@Injectable({ providedIn: 'root' })
export class SupportService {
  constructor(private readonly http: HttpClient) {}

  listTickets(): Observable<SupportTicket[]> {
    return this.http.get<SupportTicket[]>(`${API_BASE_URL}/support/tickets`);
  }

  createTicket(payload: TicketPayload): Observable<SupportTicket> {
    return this.http.post<SupportTicket>(`${API_BASE_URL}/support/tickets`, payload);
  }

  getTicket(id: string): Observable<SupportTicket> {
    return this.http.get<SupportTicket>(`${API_BASE_URL}/support/tickets/${id}`);
  }
}
