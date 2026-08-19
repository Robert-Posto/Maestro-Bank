import { Injectable, signal } from '@angular/core';

export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'maestrobank_theme';

/**
 * Temă claro/dark — comută `data-theme` pe <html>, care re-declanșează
 * tokenii din styles.css (:root[data-theme='dark']). Preferința persistă
 * în localStorage (nu sessionStorage — vrem să rămână peste sesiuni, spre
 * deosebire de JWT). Dacă userul n-a ales niciodată, pornim de la
 * preferința sistemului (prefers-color-scheme), dar din acel moment alegerea
 * explicită a userului are mereu prioritate.
 */
@Injectable({ providedIn: 'root' })
export class ThemeService {
  private readonly _theme = signal<Theme>(this.resolveInitialTheme());
  readonly theme = this._theme.asReadonly();

  constructor() {
    this.applyToDocument(this._theme());
  }

  toggle(): void {
    this.set(this._theme() === 'dark' ? 'light' : 'dark');
  }

  set(theme: Theme): void {
    this._theme.set(theme);
    localStorage.setItem(STORAGE_KEY, theme);
    this.applyToDocument(theme);
  }

  private resolveInitialTheme(): Theme {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'light' || stored === 'dark') {
      return stored;
    }
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  private applyToDocument(theme: Theme): void {
    document.documentElement.setAttribute('data-theme', theme);
  }
}
