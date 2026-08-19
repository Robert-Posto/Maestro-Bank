import { Component, input } from '@angular/core';

/** Titlu + subtitlu de pagină, consistent pe toate ecranele /app/*. */
@Component({
  selector: 'app-page-header',
  standalone: true,
  template: `
    <div class="page-header">
      <div>
        <h1>{{ title() }}</h1>
        @if (subtitle()) {
          <p class="page-header__subtitle">{{ subtitle() }}</p>
        }
      </div>
      <div class="page-header__actions">
        <ng-content />
      </div>
    </div>
  `,
  styles: [
    `
      .page-header {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: var(--mb-space-4);
        margin-bottom: var(--mb-space-6);
        flex-wrap: wrap;
      }
      .page-header h1 {
        font-size: var(--mb-font-size-xl);
      }
      .page-header__subtitle {
        margin-top: var(--mb-space-1);
        color: var(--mb-text-secondary);
        font-size: var(--mb-font-size-sm);
      }
      .page-header__actions {
        display: flex;
        align-items: center;
        gap: var(--mb-space-3);
      }
    `,
  ],
})
export class PageHeader {
  readonly title = input.required<string>();
  readonly subtitle = input<string | undefined>(undefined);
}
