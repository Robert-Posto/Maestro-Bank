import { Component, HostListener, input, output } from '@angular/core';

import { TranslatePipe } from '../../pipes/translate.pipe';

/** Overlay generic reutilizabil — folosit de ConfirmDialog și de orice formular modal (ex. Add beneficiary). */
@Component({
  selector: 'app-modal',
  standalone: true,
  imports: [TranslatePipe],
  template: `
    <div class="modal-backdrop" (click)="closed.emit()">
      <div class="modal-panel" [style.maxWidth.px]="maxWidth()" (click)="$event.stopPropagation()">
        <div class="modal-header">
          <h3>{{ title() }}</h3>
          <button type="button" class="modal-close" [attr.aria-label]="'common.close' | translate" (click)="closed.emit()">×</button>
        </div>
        <div class="modal-body">
          <ng-content />
        </div>
      </div>
    </div>
  `,
  styles: [
    `
      .modal-backdrop {
        position: fixed;
        inset: 0;
        background: rgba(10, 18, 38, 0.45);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 1100;
        padding: var(--mb-space-4);
        animation: modal-fade 140ms ease;
      }
      .modal-panel {
        background: var(--mb-surface);
        border-radius: var(--mb-radius-lg);
        box-shadow: var(--mb-shadow-lg);
        width: 100%;
        max-height: 90vh;
        overflow-y: auto;
        animation: modal-pop 160ms ease;
      }
      .modal-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: var(--mb-space-5) var(--mb-space-6);
        border-bottom: 1px solid var(--mb-border);
      }
      .modal-header h3 {
        font-size: var(--mb-font-size-md);
      }
      .modal-close {
        border: none;
        background: transparent;
        font-size: 1.25rem;
        line-height: 1;
        color: var(--mb-text-tertiary);
        cursor: pointer;
        padding: var(--mb-space-1);
      }
      .modal-body {
        padding: var(--mb-space-6);
      }
      @keyframes modal-fade {
        from {
          opacity: 0;
        }
        to {
          opacity: 1;
        }
      }
      @keyframes modal-pop {
        from {
          transform: translateY(8px) scale(0.98);
          opacity: 0;
        }
        to {
          transform: translateY(0) scale(1);
          opacity: 1;
        }
      }
    `,
  ],
})
export class Modal {
  readonly title = input('');
  readonly maxWidth = input(480);
  readonly closed = output<void>();

  @HostListener('document:keydown.escape')
  onEscape(): void {
    this.closed.emit();
  }
}
