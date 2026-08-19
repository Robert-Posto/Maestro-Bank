import { Component, computed, input } from '@angular/core';

export type BadgeTone = 'success' | 'warning' | 'error' | 'info' | 'neutral';

const STATUS_TONE_MAP: Record<string, BadgeTone> = {
  active: 'success',
  completed: 'success',
  resolved: 'success',
  open: 'info',
  pending: 'warning',
  in_progress: 'warning',
  frozen: 'error',
  failed: 'error',
  inactive: 'neutral',
  disabled: 'neutral',
};

const STATUS_LABEL_MAP: Record<string, string> = {
  active: 'Activ',
  completed: 'Procesată',
  pending: 'În procesare',
  failed: 'Eșuată',
  resolved: 'Rezolvat',
  open: 'Deschis',
  in_progress: 'În lucru',
  frozen: 'Blocat',
  inactive: 'Inactiv',
  disabled: 'Dezactivat',
};

/** Badge de status reutilizabil — vezi "Status" pe carduri/tranzacții/tickete. */
@Component({
  selector: 'app-status-badge',
  standalone: true,
  template: `<span class="badge" [class]="'badge--' + tone()">{{ label() }}</span>`,
  styles: [
    `
      .badge {
        display: inline-flex;
        align-items: center;
        gap: 0.35em;
        padding: 0.2rem 0.6rem;
        border-radius: var(--mb-radius-pill);
        font-size: var(--mb-font-size-xs);
        font-weight: var(--mb-font-weight-medium);
        white-space: nowrap;
      }
      .badge--success {
        background: var(--mb-positive-bg);
        color: var(--mb-positive);
      }
      .badge--warning {
        background: var(--mb-warning-bg);
        color: var(--mb-warning);
      }
      .badge--error {
        background: var(--mb-negative-bg);
        color: var(--mb-negative);
      }
      .badge--info {
        background: var(--mb-info-bg);
        color: var(--mb-info);
      }
      .badge--neutral {
        background: var(--mb-surface-muted);
        color: var(--mb-text-secondary);
        border: 1px solid var(--mb-border);
      }
    `,
  ],
})
export class StatusBadge {
  readonly status = input.required<string>();
  readonly toneOverride = input<BadgeTone | undefined>(undefined);
  readonly labelOverride = input<string | undefined>(undefined);

  protected readonly tone = computed<BadgeTone>(() => this.toneOverride() ?? STATUS_TONE_MAP[this.status()] ?? 'neutral');
  protected readonly label = computed(() => this.labelOverride() ?? STATUS_LABEL_MAP[this.status()] ?? this.status());
}
