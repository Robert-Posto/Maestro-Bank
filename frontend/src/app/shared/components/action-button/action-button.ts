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
          opacity var(--mb-transition-fast);
        white-space: nowrap;
      }
      .btn:disabled {
        opacity: 0.55;
        cursor: not-allowed;
      }
      .btn--full {
        width: 100%;
      }
      .btn--primary {
        background: var(--mb-blue-500);
        color: #fff;
      }
      .btn--primary:not(:disabled):hover {
        background: var(--mb-blue-600);
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
