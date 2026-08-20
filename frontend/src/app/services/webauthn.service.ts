import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { browserSupportsWebAuthn, startAuthentication, startRegistration } from '@simplewebauthn/browser';

import { API_BASE_URL } from '../core/api-config';
import { AuthService } from './auth.service';

interface WebauthnOptionsResponse {
  challenge_id: string;
  options: Record<string, unknown>;
}

export interface PasskeyCredential {
  id: string;
  created_at: string;
  last_used_at: string | null;
}

/** Ceea ce accounts-service::reveal_card cere pentru varianta biometrică
 * a CardRevealRequest — vezi banking.service.ts::revealCard. */
export interface WebauthnStepUpProof {
  webauthn_challenge_id: string;
  webauthn_assertion: Record<string, unknown>;
}

/**
 * Wrapper peste @simplewebauthn/browser + rutele /auth/webauthn/* din
 * auth-service. Metodele de ceremonie (register/login/step-up) sunt
 * async (nu Observable) — navigator.credentials.create()/get() sunt deja
 * Promise-based, nu are sens să le reîmbrăcăm.
 *
 * NU decidem NICIODATĂ noi dacă autentificarea a reușit — orice succes
 * "aparent" al startRegistration/startAuthentication tot trece prin
 * verificarea server-side (register/verify, login/verify, sau reveal-ul
 * de card prin accounts-service) înainte să conteze ca reușit.
 */
@Injectable({ providedIn: 'root' })
export class WebauthnService {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);

  /** Detecție sincronă de suport — folosită ca să NU oferim deloc opțiunea
   * de passkey pe un browser care nu o suportă. */
  isSupported(): boolean {
    return browserSupportsWebAuthn();
  }

  listCredentials() {
    return this.http.get<PasskeyCredential[]>(`${API_BASE_URL}/auth/webauthn/credentials`);
  }

  revokeCredential(credentialId: string) {
    return this.http.delete<void>(`${API_BASE_URL}/auth/webauthn/credentials/${credentialId}`);
  }

  /** Înregistrează un passkey nou pentru userul curent (autentificat prin
   * JWT — vezi register/options, protejat la Gateway). */
  async registerPasskey(): Promise<void> {
    const optionsResponse = await firstValueFrom(
      this.http.post<WebauthnOptionsResponse>(`${API_BASE_URL}/auth/webauthn/register/options`, {}),
    );
    const credential = await startRegistration({ optionsJSON: optionsResponse.options as never });
    await firstValueFrom(
      this.http.post(`${API_BASE_URL}/auth/webauthn/register/verify`, {
        challenge_id: optionsResponse.challenge_id,
        credential,
      }),
    );
  }

  /** Autentificare cu passkey, ca alternativă la parolă — adoptă tokenul
   * rezultat prin AuthService.setToken, exact ca la login cu parolă
   * (aceeași sursă de adevăr pentru sesiune). */
  async loginWithPasskey(email: string): Promise<void> {
    const optionsResponse = await firstValueFrom(
      this.http.post<WebauthnOptionsResponse>(`${API_BASE_URL}/auth/webauthn/login/options`, { email }),
    );
    const credential = await startAuthentication({ optionsJSON: optionsResponse.options as never });
    const tokenResponse = await firstValueFrom(
      this.http.post<{ access_token: string }>(`${API_BASE_URL}/auth/webauthn/login/verify`, {
        challenge_id: optionsResponse.challenge_id,
        credential,
      }),
    );
    this.auth.setToken(tokenResponse.access_token);
  }

  /** Cere o reconfirmare biometrică pentru o acțiune sensibilă (ex. reveal
   * card) — `actionPayload` trebuie să fie valoarea REZOLVATĂ server-side
   * (ex. card_id-ul din URL), niciodată una aleasă liber de UI, ca
   * assertion-ul rezultat să fie legat strict de acțiunea respectivă. */
  async getStepUpAssertion(action: string, actionPayload: string): Promise<WebauthnStepUpProof> {
    const optionsResponse = await firstValueFrom(
      this.http.post<WebauthnOptionsResponse>(`${API_BASE_URL}/auth/webauthn/stepup/options`, {
        action,
        action_payload: actionPayload,
      }),
    );
    const assertion = await startAuthentication({ optionsJSON: optionsResponse.options as never });
    return {
      webauthn_challenge_id: optionsResponse.challenge_id,
      webauthn_assertion: assertion as unknown as Record<string, unknown>,
    };
  }
}
