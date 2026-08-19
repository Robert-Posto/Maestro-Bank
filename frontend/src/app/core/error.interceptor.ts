import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';

import { AuthService } from '../services/auth.service';

/**
 * Dacă orice cerere protejată răspunde cu 401 (token expirat/invalid),
 * curăță sesiunea și trimite userul înapoi la /login — altfel pagina ar
 * rămâne blocată afișând erori generice fără nicio cale de ieșire.
 * Cererile de /auth/login și /auth/register sunt excluse (401 acolo
 * înseamnă "credențiale greșite", nu "sesiune expirată").
 */
export const errorInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const router = inject(Router);

  return next(req).pipe(
    catchError((error: unknown) => {
      if (
        error instanceof HttpErrorResponse &&
        error.status === 401 &&
        !req.url.includes('/auth/login') &&
        !req.url.includes('/auth/register')
      ) {
        auth.logout();
        router.navigate(['/login'], { queryParams: { sessionExpired: '1' } });
      }
      return throwError(() => error);
    }),
  );
};
