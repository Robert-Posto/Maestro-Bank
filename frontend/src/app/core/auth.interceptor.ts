import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';

import { AuthService } from '../services/auth.service';

/**
 * Atașează automat `Authorization: Bearer <token>` cererilor HTTP, dacă
 * userul e autentificat (token prezent în sessionStorage — vezi
 * AuthService pentru nota despre limitările acestei abordări în
 * development).
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const token = auth.getToken();

  if (!token) {
    return next(req);
  }

  return next(req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }));
};
