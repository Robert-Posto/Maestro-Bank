import { Component, computed, inject, input, output } from '@angular/core';

import { ActionButton } from '../action-button/action-button';
import { Modal } from '../modal/modal';
import { LanguageService } from '../../../services/language.service';

/**
 * Confirmare pentru acțiuni ireversibile/importante (ex. Delete budget,
 * Delete beneficiary). Uz:
 *   @if (pendingDelete()) {
 *     <app-confirm-dialog title="Șterge bugetul?" message="..."
 *       confirmLabel="Șterge" (confirmed)="doDelete()" (cancelled)="pendingDelete.set(null)" />
 *   }
 */
@Component({
  selector: 'app-confirm-dialog',
  standalone: true,
  imports: [Modal, ActionButton],
  template: `
    <app-modal [title]="title() ?? defaultTitle()" [maxWidth]="420" (closed)="cancelled.emit()">
      <p class="confirm-message">{{ message() }}</p>
      <div class="confirm-actions">
        <app-action-button variant="secondary" (pressed)="cancelled.emit()">{{ cancelLabel() ?? defaultCancelLabel() }}</app-action-button>
        <app-action-button [variant]="danger() ? 'danger' : 'primary'" [loading]="loading()" (pressed)="confirmed.emit()">
          {{ confirmLabel() ?? defaultConfirmLabel() }}
        </app-action-button>
      </div>
    </app-modal>
  `,
  styles: [
    `
      .confirm-message {
        color: var(--mb-text-secondary);
        font-size: var(--mb-font-size-sm);
        line-height: var(--mb-line-height-base);
        margin-bottom: var(--mb-space-5);
      }
      .confirm-actions {
        display: flex;
        justify-content: flex-end;
        gap: var(--mb-space-3);
      }
    `,
  ],
})
export class ConfirmDialog {
  private readonly language = inject(LanguageService);

  readonly title = input<string | undefined>(undefined);
  readonly message = input('');
  readonly confirmLabel = input<string | undefined>(undefined);
  readonly cancelLabel = input<string | undefined>(undefined);
  readonly danger = input(false);
  readonly loading = input(false);
  readonly confirmed = output<void>();
  readonly cancelled = output<void>();

  protected readonly defaultTitle = computed(() => this.language.t('common.areYouSure'));
  protected readonly defaultConfirmLabel = computed(() => this.language.t('common.confirm'));
  protected readonly defaultCancelLabel = computed(() => this.language.t('common.cancel'));
}
