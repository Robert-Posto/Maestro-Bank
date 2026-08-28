import { Component, inject, input, output, signal } from '@angular/core';

import { LanguageService } from '../../../services/language.service';
import { Icon } from '../icon/icon';

/**
 * Câmp de parolă cu ochiul de arată/ascunde — un singur loc pentru
 * formula vizuală (border/padding/focus) deja duplicată identic în
 * auth-screen.css, profile.css și cards.css (reveal-form). `[value]`/
 * `(valueChange)` în loc de `[(ngModel)]`, ca să rămână un simplu
 * input()/output() (convenția componentelor mici din acest folder —
 * ActionButton, Modal, StatusBadge — niciuna nu implementează
 * ControlValueAccessor).
 */
@Component({
  selector: 'app-password-input',
  standalone: true,
  imports: [Icon],
  template: `
    <div class="password-input">
      <input
        [type]="visible() ? 'text' : 'password'"
        [value]="value()"
        (input)="onInput($event)"
        [attr.name]="name() || null"
        [attr.autocomplete]="autocomplete()"
        [attr.placeholder]="placeholder() || null"
      />
      <button
        type="button"
        class="password-input__toggle"
        [attr.aria-label]="language.t(visible() ? 'common.hidePassword' : 'common.showPassword')"
        (click)="visible.set(!visible())"
      >
        <app-icon [name]="visible() ? 'eye-off' : 'eye'" [size]="16" />
      </button>
    </div>
  `,
  styles: [
    `
      .password-input {
        position: relative;
        display: flex;
      }

      .password-input input {
        width: 100%;
        font-family: inherit;
        font-size: var(--mb-font-size-base);
        padding: 0.6rem 2.5rem 0.6rem var(--mb-space-3);
        border-radius: var(--mb-radius-sm);
        border: 1px solid var(--mb-border-strong);
        outline: none;
        color: var(--mb-text-primary);
        background: var(--mb-surface);
        transition:
          border-color var(--mb-transition-fast),
          box-shadow var(--mb-transition-fast);
      }

      .password-input input:focus {
        border-color: var(--mb-blue-500);
        box-shadow: 0 0 0 3px rgba(47, 111, 237, 0.12);
      }

      .password-input__toggle {
        position: absolute;
        top: 50%;
        right: 4px;
        transform: translateY(-50%);
        display: grid;
        place-items: center;
        width: 30px;
        height: 30px;
        border: none;
        border-radius: 50%;
        background: transparent;
        color: var(--mb-text-tertiary);
        cursor: pointer;
        transition:
          background var(--mb-transition-fast),
          color var(--mb-transition-fast);
      }

      .password-input__toggle:hover {
        background: var(--mb-surface-muted);
        color: var(--mb-text-secondary);
      }
    `,
  ],
})
export class PasswordInput {
  protected readonly language = inject(LanguageService);

  readonly value = input('');
  readonly name = input('');
  readonly placeholder = input('');
  readonly autocomplete = input<'current-password' | 'new-password'>('current-password');
  readonly valueChange = output<string>();

  protected readonly visible = signal(false);

  protected onInput(event: Event): void {
    this.valueChange.emit((event.target as HTMLInputElement).value);
  }
}
