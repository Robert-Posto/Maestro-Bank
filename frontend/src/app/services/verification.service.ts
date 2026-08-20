import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../core/api-config';

export interface VerificationResult {
  verified: boolean;
  message: string;
  similarity_percent: number | null;
}

/**
 * Verificare identitate (buletin vs. selfie) — vezi backend
 * verification-service (DeepFace). Un singur endpoint, multipart/form-data
 * (2 imagini), fără JSON — de-aia nu trece prin restul serviciilor "*.service.ts"
 * care presupun JSON.
 */
@Injectable({ providedIn: 'root' })
export class VerificationService {
  constructor(private readonly http: HttpClient) {}

  verifyIdentity(idDocument: Blob, selfie: Blob): Observable<VerificationResult> {
    const formData = new FormData();
    formData.append('id_document', idDocument, 'id_document.jpg');
    formData.append('selfie', selfie, 'selfie.jpg');
    return this.http.post<VerificationResult>(`${API_BASE_URL}/verification/verify-identity`, formData);
  }
}
