import { Pipe, PipeTransform, inject } from '@angular/core';

import { LanguageService } from '../../services/language.service';

/**
 * `{{ 'nav.overview' | translate }}` — traduce o cheie din shared/i18n
 * după limba activă (LanguageService). IMPUR intenționat (`pure: false`):
 * un pipe pur re-rulează DOAR când argumentul lui (cheia) se schimbă, nu
 * și când un semnal citit INTERN (limba) se schimbă — fără asta, comutarea
 * limbii n-ar actualiza text deja randat, exact bug-ul pe care ochiul
 * "funcțional pe toate paginile" nu are voie să-l aibă.
 */
@Pipe({ name: 'translate', standalone: true, pure: false })
export class TranslatePipe implements PipeTransform {
  private readonly language = inject(LanguageService);

  transform(key: string): string {
    return this.language.t(key);
  }
}
