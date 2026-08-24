import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { AuthService, AuthUser } from '../services/auth.service';

/** Aduce userul curent (din signal, dacă e deja încărcat — ex. navigare
 * internă — sau printr-un fetch, la refresh direct pe o rută). `null`
 * dacă tokenul e invalid/expirat. */
async function resolveCurrentUser(auth: AuthService): Promise<AuthUser | null> {
  const cached = auth.currentUser();
  if (cached) return cached;
  try {
    return await firstValueFrom(auth.fetchCurrentUser());
  } catch {
    return null;
  }
}

/**
 * Protejează rutele /app/* — redirecționează la /login dacă userul nu are
 * un JWT valid în sessionStorage, ȘI la pasul de onboarding corespunzător
 * dacă nu a terminat verificarea email/identitate (vezi routes 'onboarding'
 * din app.routes.ts). Vezi AuthService pentru nota despre limitările
 * abordării curente cu tokenul (dev-only, nu arhitectură de producție).
 */
export const authGuard: CanActivateFn = async () => {
  const auth = inject(AuthService);
  const router = inject(Router);

  if (!auth.isAuthenticated()) {
    return router.createUrlTree(['/login']);
  }

  const user = await resolveCurrentUser(auth);
  if (!user) {
    return router.createUrlTree(['/login']);
  }
  if (!user.email_verified) {
    return router.createUrlTree(['/onboarding/verify-email']);
  }
  if (!user.identity_verified) {
    return router.createUrlTree(['/onboarding/verify-identity']);
  }

  return true;
};

/** Invers — /login și /register redirecționează la /app/overview dacă userul e deja autentificat. */
export const guestGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);

  if (!auth.isAuthenticated()) {
    return true;
  }

  return router.createUrlTree(['/app/overview']);
};

/** Ecranele de onboarding cer doar autentificare — userul poate fi
 * neverificat pe unul sau ambele fronturi, exact de-aia e aici. */
export const onboardingAuthGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);

  if (auth.isAuthenticated()) {
    return true;
  }

  return router.createUrlTree(['/login']);
};

/** /onboarding/verify-identity cere email deja verificat — altfel înapoi
 * la pasul 1. Dacă userul e deja complet verificat (revizitare directă a
 * URL-ului), îl trimitem direct în aplicație, nu-l punem să repete pasul. */
export const onboardingIdentityGuard: CanActivateFn = async () => {
  const auth = inject(AuthService);
  const router = inject(Router);

  if (!auth.isAuthenticated()) {
    return router.createUrlTree(['/login']);
  }

  const user = await resolveCurrentUser(auth);
  if (!user) {
    return router.createUrlTree(['/login']);
  }
  if (!user.email_verified) {
    return router.createUrlTree(['/onboarding/verify-email']);
  }
  if (user.identity_verified) {
    return router.createUrlTree(['/app/overview']);
  }

  return true;
};
