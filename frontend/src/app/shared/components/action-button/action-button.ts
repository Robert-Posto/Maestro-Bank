import { Component, input, output } from '@angular/core';

export type ActionButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';

/** Buton reutilizabil, cu variante + stare loading — nu reface stilul de buton în fiecare pagină. */
@Component({
  selector: 'app-action-button',
  standalone: true,
  template: `
    <button
      [type]="type()"
      class="btn"
      [class]="'btn--' + variant() + (fullWidth() ? ' btn--full' : '')"
      [disabled]="disabled() || loading()"
      (click)="pressed.emit()"
    >
      @if (loading()) {
        <span class="btn__spinner" aria-hidden="true"></span>
      }
      <ng-content />
    </button>
  `,
  styles: [
    `
      .btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: var(--mb-space-2);
        font-family: inherit;
        font-size: var(--mb-font-size-sm);
        font-weight: var(--mb-font-weight-medium);
        padding: 0.65rem 1.1rem;
        border-radius: var(--mb-radius-sm);
        border: 1px solid transparent;
        cursor: pointer;
        transition:
          background var(--mb-transition-fast),
          border-color var(--mb-transition-fast),
          opacity var(--mb-transition-fast),
          box-shadow var(--mb-transition-fast),
          transform var(--mb-transition-fast);
        white-space: nowrap;
      }
      .btn:disabled {
        opacity: 0.55;
        cursor: not-allowed;
      }
      .btn--full {
        width: 100%;
      }
      /* Umbră + lift discret la hover — butonul primar apare pe aproape
         fiecare formular din aplicație, deci o singură nuanță de "apăsabil"
         în plus aici se simte pe toată aplicația, nu doar într-un loc. */
      .btn--primary {
        background: var(--mb-blue-500);
        color: #fff;
        box-shadow: 0 2px 8px -2px rgba(47, 111, 237, 0.35);
      }
      .btn--primary:not(:disabled):hover {
        background: var(--mb-blue-600);
        box-shadow: 0 6px 16px -4px rgba(47, 111, 237, 0.42);
        transform: translateY(-1px);
      }
      .btn--primary:not(:disabled):active {
        transform: translateY(0);
        box-shadow: 0 2px 6px -2px rgba(47, 111, 237, 0.35);
      }
      .btn--secondary {
        background: var(--mb-surface);
        border-color: var(--mb-border-strong);
        color: var(--mb-text-primary);
      }
      .btn--secondary:not(:disabled):hover {
        border-color: var(--mb-blue-500);
        color: var(--mb-blue-600);
      }
      .btn--ghost {
        background: transparent;
        color: var(--mb-text-secondary);
      }
      .btn--ghost:not(:disabled):hover {
        background: var(--mb-surface-muted);
        color: var(--mb-text-primary);
      }
      .btn--danger {
        background: var(--mb-negative-bg);
        color: var(--mb-negative);
      }
      .btn--danger:not(:disabled):hover {
        background: var(--mb-negative);
        color: #fff;
      }
      .btn__spinner {
        width: 14px;
        height: 14px;
        border-radius: 50%;
        border: 2px solid currentColor;
        border-right-color: transparent;
        animation: btn-spin 0.6s linear infinite;
      }
      @keyframes btn-spin {
        to {
          transform: rotate(360deg);
        }
      }
      @media (prefers-reduced-motion: reduce) {
        .btn {
          transition: background var(--mb-transition-fast), border-color var(--mb-transition-fast), opacity var(--mb-transition-fast);
        }
        .btn--primary:not(:disabled):hover,
        .btn--primary:not(:disabled):active {
          transform: none;
        }
      }
    `,
  ],
})
export class ActionButton {
  readonly variant = input<ActionButtonVariant>('primary');
  readonly type = input<'button' | 'submit'>('button');
  readonly disabled = input(false);
  readonly loading = input(false);
  readonly fullWidth = input(false);
  readonly pressed = output<void>();
}
