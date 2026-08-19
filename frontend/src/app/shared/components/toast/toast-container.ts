import { Component, inject } from '@angular/core';

import { ToastService } from './toast.service';

@Component({
  selector: 'app-toast-container',
  standalone: true,
  template: `
    <div class="toast-stack" role="status" aria-live="polite">
      @for (toast of toasts(); track toast.id) {
        <div class="toast" [class]="'toast--' + toast.kind">
          <span class="toast__text">{{ toast.text }}</span>
          <button type="button" class="toast__close" (click)="toastService.dismiss(toast.id)" aria-label="Închide">
            ×
          </button>
        </div>
      }
    </div>
  `,
  styles: [
    `
      .toast-stack {
        position: fixed;
        top: var(--mb-space-6);
        right: var(--mb-space-6);
        z-index: 1000;
        display: flex;
        flex-direction: column;
        gap: var(--mb-space-2);
        max-width: 380px;
      }

      .toast {
        display: flex;
        align-items: center;
        gap: var(--mb-space-3);
        padding: var(--mb-space-3) var(--mb-space-4);
        border-radius: var(--mb-radius-md);
        background: var(--mb-surface);
        box-shadow: var(--mb-shadow-lg);
        border: 1px solid var(--mb-border);
        font-size: var(--mb-font-size-sm);
        color: var(--mb-text-primary);
        animation: toast-in 160ms ease;
      }

      .toast--success {
        border-left: 3px solid var(--mb-positive);
      }
      .toast--error {
        border-left: 3px solid var(--mb-negative);
      }
      .toast--info {
        border-left: 3px solid var(--mb-info);
      }

      .toast__text {
        flex: 1;
      }

      .toast__close {
        border: none;
        background: transparent;
        color: var(--mb-text-tertiary);
        font-size: 1.1rem;
        line-height: 1;
        cursor: pointer;
        padding: 0;
      }

      @keyframes toast-in {
        from {
          opacity: 0;
          transform: translateY(-6px);
        }
        to {
          opacity: 1;
          transform: translateY(0);
        }
      }
    `,
  ],
})
export class ToastContainer {
  protected readonly toastService = inject(ToastService);
  protected readonly toasts = this.toastService.toasts;
}
