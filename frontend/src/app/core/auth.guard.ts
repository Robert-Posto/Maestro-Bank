import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { AuthService } from '../services/auth.service';

/**
 * Protejează rutele /app/* — redirecționează la /login dacă userul nu are
 * un JWT valid în sessionStorage. Vezi AuthService pentru nota despre
 * limitările acestei abordări (dev-only, nu arhitectură de producție).
 */
export const authGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);

  if (auth.isAuthenticated()) {
    return true;
  }

  return router.createUrlTree(['/login']);
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
