import { Component, inject } from '@angular/core';

import { LanguageService } from '../../../services/language.service';
import { Icon } from '../icon/icon';

/**
 * Comutator RO/EN pentru cele 5 pagini fără niciun shell comun (login,
 * register, verify-email, verify-identity, welcome — vezi planul fazei).
 * Un singur loc, inserat identic în fiecare din cele 5, în loc de 5 copii
 * ale aceleiași bucăți de markup.
 */
@Component({
  selector: 'app-auth-language-toggle',
  standalone: true,
  imports: [Icon],
  template: `
    <button
      type="button"
      class="auth-language-toggle"
      [attr.title]="language.language() === 'ro' ? 'English' : 'Română'"
      (click)="language.toggle()"
    >
      <app-icon name="globe" [size]="15" />
      {{ language.language() === 'ro' ? 'RO' : 'EN' }}
    </button>
  `,
  styles: [
    `
      .auth-language-toggle {
        position: fixed;
        top: var(--mb-space-5);
        right: var(--mb-space-5);
        z-index: 20;
        display: inline-flex;
        align-items: center;
        gap: 5px;
        padding: 0.4rem 0.7rem;
        border-radius: var(--mb-radius-pill);
        border: 1px solid var(--mb-border-strong);
        background: var(--mb-surface);
        color: var(--mb-text-secondary);
        font-family: inherit;
        font-size: var(--mb-font-size-xs);
        font-weight: var(--mb-font-weight-semibold);
        cursor: pointer;
        transition:
          background var(--mb-transition-fast),
          color var(--mb-transition-fast);
      }

      .auth-language-toggle:hover {
        background: var(--mb-surface-muted);
        color: var(--mb-text-primary);
      }
    `,
  ],
})
export class AuthLanguageToggle {
  protected readonly language = inject(LanguageService);
}
