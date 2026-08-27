import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../core/api-config';
import { WebauthnStepUpProof } from './webauthn.service';

export type DocumentStatus = 'pending' | 'signed' | 'cancelled';

export interface DocumentSummary {
  id: string;
  title: string;
  status: DocumentStatus;
  created_at: string;
  signed_at: string | null;
}

export interface DocumentView extends DocumentSummary {
  pdf_data: string;
}

export type DocumentSignProof = { password: string } | WebauthnStepUpProof;

/** support-service, prin /api/support/documents — documente de semnat
 * (eSign) trimise de personal, vezi shared/components/staff-documents
 * pentru partea de personal. */
@Injectable({ providedIn: 'root' })
export class DocumentsService {
  constructor(private readonly http: HttpClient) {}

  listMyDocuments(): Observable<DocumentSummary[]> {
    return this.http.get<DocumentSummary[]>(`${API_BASE_URL}/support/documents`);
  }

  getDocument(id: string): Observable<DocumentView> {
    return this.http.get<DocumentView>(`${API_BASE_URL}/support/documents/${id}`);
  }

  signDocument(id: string, proof: DocumentSignProof): Observable<DocumentSummary> {
    return this.http.post<DocumentSummary>(`${API_BASE_URL}/support/documents/${id}/sign`, proof);
  }
}
