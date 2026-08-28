import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';

import { LanguageService } from '../services/language.service';

/**
 * Atașează `X-Language: ro|en` fiecărei cereri — mirror exact pe
 * auth.interceptor.ts (Authorization). Backend-ul citește acest header ca
 * să traducă text generat dinamic (erori, notificări, Guardian) — vezi
 * planul fazei de comutator de limbă. Gateway-ul trece toate header-ele
 * non-hop-by-hop mai departe neschimbat, deci niciun cod nou nu e necesar
 * acolo.
 */
export const languageInterceptor: HttpInterceptorFn = (req, next) => {
  const language = inject(LanguageService);
  return next(req.clone({ setHeaders: { 'X-Language': language.language() } }));
};
