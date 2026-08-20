import { Injectable, inject } from '@angular/core';
import { Router } from '@angular/router';

import { AuthService } from './auth.service';

/** Cât timp fără nicio activitate (mouse/tastatură/scroll/atingere)
 * înainte de deconectare automată. */
export const IDLE_TIMEOUT_MS = 60_000;

const ACTIVITY_EVENTS = ['mousemove', 'mousedown', 'keydown', 'scroll', 'touchstart'] as const;

/**
 * Deconectare automată la inactivitate — pornită DOAR cât timp userul e în
 * /app/* (vezi AppShell), niciodată pe login/register/onboarding. Refolosește
 * exact fluxul existent de "sesiune expirată" din Login (query param
 * sessionExpired=1), ca userul să vadă același mesaj, indiferent dacă
 * tokenul a expirat efectiv sau doar a stat prea mult neatins laptopul.
 */
@Injectable({ providedIn: 'root' })
export class IdleService {
  private readonly router = inject(Router);
  private readonly auth = inject(AuthService);

  private timer?: ReturnType<typeof setTimeout>;
  private readonly onActivity = () => this.resetTimer();

  start(): void {
    ACTIVITY_EVENTS.forEach((event) => document.addEventListener(event, this.onActivity, { passive: true }));
    this.resetTimer();
  }

  stop(): void {
    ACTIVITY_EVENTS.forEach((event) => document.removeEventListener(event, this.onActivity));
    clearTimeout(this.timer);
  }

  private resetTimer(): void {
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.onIdleTimeout(), IDLE_TIMEOUT_MS);
  }

  private onIdleTimeout(): void {
    this.stop();
    this.auth.logout();
    this.router.navigate(['/login'], { queryParams: { sessionExpired: 1 } });
  }
}
