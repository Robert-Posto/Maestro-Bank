import { Component, computed, input } from '@angular/core';

export type BadgeTone = 'success' | 'warning' | 'error' | 'info' | 'neutral';

const STATUS_TONE_MAP: Record<string, BadgeTone> = {
  active: 'success',
  completed: 'success',
  resolved: 'success',
  open: 'info',
  pending: 'warning',
  pending_review: 'warning',
  in_progress: 'warning',
  frozen: 'error',
  failed: 'error',
  rejected: 'error',
  cancelled: 'neutral',
  inactive: 'neutral',
  disabled: 'neutral',
  matured_renewed: 'info',
  liquidated_early: 'warning',
  closed_paid_out: 'neutral',
};

const STATUS_LABEL_MAP: Record<string, string> = {
  active: 'Activ',
  completed: 'Procesată',
  pending: 'În procesare',
  // Reținut de motorul de fraud (scor peste prag) — vezi backend app/holds.py.
  pending_review: 'Reținut pentru verificare',
  failed: 'Eșuată',
  // Refuz direct BEN-04 (beneficiar pe blocklist) — vezi backend
  // app/blocklist.py/app/service.py::create_transfer. Distinct de "failed"
  // (eroare tehnică/ledger) — aici e o decizie deliberată a băncii.
  rejected: 'Refuzată — beneficiar blocat',
  resolved: 'Rezolvat',
  open: 'Deschis',
  in_progress: 'În lucru',
  frozen: 'Blocat',
  cancelled: 'Anulată',
  inactive: 'Inactiv',
  disabled: 'Dezactivat',
  matured_renewed: 'Reînnoit automat',
  liquidated_early: 'Lichidat anticipat',
  closed_paid_out: 'Plătit la scadență',
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
