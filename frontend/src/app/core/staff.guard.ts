import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { AuthService } from '../services/auth.service';
import { decodeJwtPayload } from '../shared/jwt-utils';

/**
 * Protejează /app/staff/* — SUPLIMENTAR față de authGuard de pe părintele
 * /app (care rulează oricum întâi). Decodează JWT-ul DOAR ca indiciu de UI
 * (la fel ca restul decodărilor din jwt-utils.ts) — un client cu un rol
 * modificat manual în token tot ar primi 403 de la require_staff pe orice
 * apel real către backend (transactions-service/app/security.py), deci
 * asta nu e o gaură de securitate, doar evită afișarea unui ecran gol/eroare
 * unui customer care ar naviga direct la /app/staff/... din URL.
 */
export const staffGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);

  const token = auth.getToken();
  const role = token ? decodeJwtPayload(token)?.role : null;

  if (role === 'staff') {
    return true;
  }

  return router.createUrlTree(['/app/overview']);
};
