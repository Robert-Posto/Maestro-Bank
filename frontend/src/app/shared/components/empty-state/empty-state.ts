import { Component, computed, inject, input } from '@angular/core';

import { Icon } from '../icon/icon';
import { LanguageService } from '../../../services/language.service';

/**
 * Stare "gol" reutilizabilă — "No transactions yet", "No budgets yet" etc.
 * (vezi task-ul MaestroBank, secțiunea 27). Nu afișa niciodată un tabel/listă
 * goală fără context.
 */
@Component({
  selector: 'app-empty-state',
  standalone: true,
  imports: [Icon],
  template: `
    <div class="empty-state">
      <div class="empty-state__icon" aria-hidden="true">
        <app-icon [name]="icon()" [size]="26" />
      </div>
      <p class="empty-state__title">{{ title() ?? defaultTitle() }}</p>
      @if (description()) {
        <p class="empty-state__description">{{ description() }}</p>
      }
      <ng-content />
    </div>
  `,
  styles: [
    `
      .empty-state {
        display: flex;
        flex-direction: column;
        align-items: center;
        text-align: center;
        padding: var(--mb-space-10) var(--mb-space-6);
        color: var(--mb-text-secondary);
      }
      .empty-state__icon {
        display: inline-flex;
        margin-bottom: var(--mb-space-3);
        opacity: 0.5;
      }
      .empty-state__title {
        font-weight: var(--mb-font-weight-medium);
        color: var(--mb-text-primary);
        margin-bottom: var(--mb-space-1);
      }
      .empty-state__description {
        font-size: var(--mb-font-size-sm);
        max-width: 360px;
      }
    `,
  ],
})
export class EmptyState {
  private readonly language = inject(LanguageService);

  readonly icon = input('info');
  readonly title = input<string | undefined>(undefined);
  readonly description = input<string | undefined>(undefined);

  protected readonly defaultTitle = computed(() => this.language.t('common.nothingToShow'));
}
