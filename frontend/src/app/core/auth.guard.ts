import { inject } from '@angular/core';
import { CanActivateFn, Router, RouterStateSnapshot } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { AuthService, AuthUser } from '../services/auth.service';

/** Aduce userul curent (din signal, dacă e deja încărcat — ex. navigare
 * internă — sau printr-un fetch, la refresh direct pe o rută). `null`
 * dacă tokenul e invalid/expirat — caz în care ȘTERGEM tokenul stale din
 * sessionStorage (auth.logout()) ÎNAINTE de a întoarce null. Fără asta,
 * guestGuard (mai jos) încă vede `isAuthenticated() === true` (verifică
 * doar PREZENȚA tokenului, nu validitatea lui) și te trimite instant
 * înapoi în /app -> authGuard eșuează din nou -> redirect infinit
 * /login <-> /app, cu câte un GET /auth/me la fiecare iterație (bug real,
 * observat live: userul rămâne cu un JWT valabil sintactic, dar userul lui
 * nu mai există în baza de date curentă). */
async function resolveCurrentUser(auth: AuthService): Promise<AuthUser | null> {
  const cached = auth.currentUser();
  if (cached) return cached;
  try {
    return await firstValueFrom(auth.fetchCurrentUser());
  } catch {
    auth.logout();
    return null;
  }
}

/** "Acasă" diferă după rol — personalul NU are cont de client (e emis
 * direct de bancă, doar pentru revizuit rețineri), deci nu are sens să
 * ajungă vreodată pe /app/*, nici măcar tranzitoriu. */
function homeRouteFor(user: AuthUser): string[] {
  return user.role === 'staff' ? ['/admin'] : ['/app/overview'];
}

/**
 * Protejează rutele /app/* — redirecționează la /login dacă userul nu are
 * un JWT valid în sessionStorage, la /admin dacă e personal (NU are cont
 * de client, deci /app/* nu e niciodată destinația lui — vezi AdminShell),
 * ȘI la pasul de onboarding corespunzător dacă un client nu a terminat
 * verificarea email/identitate (vezi routes 'onboarding' din app.routes.ts).
 * Vezi AuthService pentru nota despre limitările abordării curente cu
 * tokenul (dev-only, nu arhitectură de producție).
 *
 * Când redirecționează la /login, păstrează URL-ul ÎNCERCAT în query param
 * `returnUrl` — altfel cineva care deschide un link de tip "Cerere de
 * plată" (/app/pay/{id}, vezi features/pay-request) NEautentificat s-ar
 * loga și ar ajunge pe /app/overview, nu înapoi pe pagina de plată (vezi
 * Login::submit, care citește acest query param).
 */
export const authGuard: CanActivateFn = async (_route, state: RouterStateSnapshot) => {
  const auth = inject(AuthService);
  const router = inject(Router);

  if (!auth.isAuthenticated()) {
    return router.createUrlTree(['/login'], { queryParams: { returnUrl: state.url } });
  }

  const user = await resolveCurrentUser(auth);
  if (!user) {
    return router.createUrlTree(['/login'], { queryParams: { returnUrl: state.url } });
  }
  if (user.role === 'staff') {
    return router.createUrlTree(['/admin']);
  }
  if (!user.email_verified) {
    return router.createUrlTree(['/onboarding/verify-email']);
  }
  if (!user.identity_verified) {
    return router.createUrlTree(['/onboarding/verify-identity']);
  }

  return true;
};

/** Invers — /login și /register redirecționează "acasă" (diferit după
 * rol — vezi homeRouteFor) dacă userul e deja autentificat. */
export const guestGuard: CanActivateFn = async () => {
  const auth = inject(AuthService);
  const router = inject(Router);

  if (!auth.isAuthenticated()) {
    return true;
  }

  const user = await resolveCurrentUser(auth);
  if (!user) {
    return true;
  }

  return router.createUrlTree(homeRouteFor(user));
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
    return router.createUrlTree(homeRouteFor(user));
  }

  return true;
};
