import { HttpClient } from '@angular/common/http';
import { Injectable, signal } from '@angular/core';
import { Observable, tap } from 'rxjs';

import { API_BASE_URL } from '../core/api-config';
import { SUPPORT_CHAT_STORAGE_KEY } from '../core/storage-keys';

const TOKEN_STORAGE_KEY = 'maestrobank_dev_jwt';

export interface RegisterPayload {
  first_name: string;
  last_name: string;
  email: string;
  // Fictiv/neverificat momentan — vezi AuthUser.phone_number mai jos.
  phone_number: string;
  password: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface AuthUser {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  // Absent pe /auth/register (UserOut) — prezent DOAR pe /auth/me
  // (UserMeOut). role gatează /admin/* (vezi core/staff.guard.ts) — DOAR
  // ca indiciu de UI, autorizarea reală rămâne server-side (require_staff).
  // phone_number e fictiv, neverificat — vezi backend.
  role?: 'customer' | 'staff';
  phone_number?: string | null;
  email_verified?: boolean;
  identity_verified?: boolean;
  /** Data URI base64 ("data:image/...") — OPȚIONALĂ, la cererea userului.
   * Absent pe /auth/register (UserOut), prezent DOAR pe /auth/me
   * (UserMeOut) — `null`/absent -> topbar/profil cad pe inițiale. */
  profile_picture?: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface ChangePasswordPayload {
  current_password: string;
  new_password: string;
}

/**
 * ⚠️ NOTĂ IMPORTANT — implementare de DEVELOPMENT, NU arhitectură de
 * securitate pentru producție: tokenul JWT e ținut în `sessionStorage`,
 * doar ca să putem testa manual din browser fluxul register -> login ->
 * acțiuni protejate. Într-o aplicație reală, stocarea/reînnoirea
 * tokenului ar necesita o strategie mult mai atentă (ex. httpOnly
 * cookies, refresh tokens, protecție XSS/CSRF) — nu prezenta această
 * alegere drept soluție finală.
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  readonly currentUser = signal<AuthUser | null>(null);

  constructor(private readonly http: HttpClient) {}

  register(payload: RegisterPayload): Observable<AuthUser> {
    return this.http.post<AuthUser>(`${API_BASE_URL}/auth/register`, payload);
  }

  login(payload: LoginPayload): Observable<TokenResponse> {
    return this.http
      .post<TokenResponse>(`${API_BASE_URL}/auth/login`, payload)
      .pipe(tap((response) => this.setToken(response.access_token)));
  }

  fetchCurrentUser(): Observable<AuthUser> {
    return this.http.get<AuthUser>(`${API_BASE_URL}/auth/me`).pipe(tap((user) => this.currentUser.set(user)));
  }

  changePassword(payload: ChangePasswordPayload): Observable<void> {
    return this.http.post<void>(`${API_BASE_URL}/auth/change-password`, payload);
  }

  /** `dataUri` — redimensionată/comprimată ÎN BROWSER înainte de apel (vezi
   * features/profile/profile.ts) — `null` șterge poza (revine la inițiale). */
  updateProfilePicture(dataUri: string | null): Observable<AuthUser> {
    return this.http
      .patch<AuthUser>(`${API_BASE_URL}/auth/me/profile-picture`, { profile_picture: dataUri })
      .pipe(tap((user) => this.currentUser.set(user)));
  }

  verifyEmail(code: string): Observable<void> {
    return this.http.post<void>(`${API_BASE_URL}/auth/verify-email`, { code });
  }

  resendVerificationEmail(): Observable<void> {
    return this.http.post<void>(`${API_BASE_URL}/auth/resend-verification-email`, {});
  }

  logout(): void {
    sessionStorage.removeItem(TOKEN_STORAGE_KEY);
    // Conversația cu Support Agent e persistată per-tab (vezi
    // features/support/support.ts) — ștearsă aici ca userul următor de pe
    // același tab/browser să nu vadă conversația celui dinainte.
    sessionStorage.removeItem(SUPPORT_CHAT_STORAGE_KEY);
    this.currentUser.set(null);
  }

  getToken(): string | null {
    return sessionStorage.getItem(TOKEN_STORAGE_KEY);
  }

  isAuthenticated(): boolean {
    return this.getToken() !== null;
  }

  /** Public — folosit și de WebauthnService după un login reușit cu
   * passkey, ca sesiunea rezultată să fie identică cu una obținută prin
   * parolă (același storage, aceeași sursă de adevăr pentru token). */
  setToken(token: string): void {
    sessionStorage.setItem(TOKEN_STORAGE_KEY, token);
  }
}
