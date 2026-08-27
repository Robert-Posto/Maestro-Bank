import { Injectable, signal } from '@angular/core';

import { TRANSLATIONS } from '../shared/i18n';

export type Language = 'ro' | 'en';

const STORAGE_KEY = 'maestrobank_language';

/**
 * Limbă RO/EN — mirror exact pe ThemeService (temă claro/dark): semnal
 * persistat în localStorage (nu sessionStorage — supraviețuiește peste
 * sesiuni, spre deosebire de JWT), aplicat pe `<html lang>`. Dacă userul
 * n-a ales niciodată, pornim de la limba browserului; din acel moment,
 * alegerea explicită are mereu prioritate.
 */
@Injectable({ providedIn: 'root' })
export class LanguageService {
  private readonly _language = signal<Language>(this.resolveInitialLanguage());
  readonly language = this._language.asReadonly();

  constructor() {
    this.applyToDocument(this._language());
  }

  toggle(): void {
    this.set(this._language() === 'ro' ? 'en' : 'ro');
  }

  set(language: Language): void {
    this._language.set(language);
    localStorage.setItem(STORAGE_KEY, language);
    this.applyToDocument(language);
  }

  /** Traduce o cheie din dicționarul shared/i18n — cade pe cheia însăși
   * dacă lipsește (vizibil/ușor de reperat în dezvoltare, mai util decât
   * un ecran gol). */
  t(key: string): string {
    const entry = TRANSLATIONS[key];
    if (!entry) {
      return key;
    }
    return entry[this._language()];
  }

  private resolveInitialLanguage(): Language {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'ro' || stored === 'en') {
      return stored;
    }
    return navigator.language?.toLowerCase().startsWith('en') ? 'en' : 'ro';
  }

  private applyToDocument(language: Language): void {
    document.documentElement.setAttribute('lang', language);
  }
}
