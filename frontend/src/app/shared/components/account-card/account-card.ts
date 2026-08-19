import { Component, input, output } from '@angular/core';

import { MoneyPipe } from '../../pipes/money.pipe';

export interface AccountRowData {
  id: string;
  name: string;
  iban: string;
  currency: string;
  balance_minor: number;
  status: string;
}

/** Rând reutilizabil pentru "Conturile mele" (Overview + pagina Conturi). */
@Component({
  selector: 'app-account-card',
  standalone: true,
  imports: [MoneyPipe],
  template: `
    <button type="button" class="account-row" (click)="opened.emit()">
      <span class="account-row__avatar">{{ account().currency }}</span>
      <span class="account-row__info">
        <span class="account-row__name">{{ account().name }}</span>
        <span class="account-row__iban">{{ account().iban }}</span>
      </span>
      <span class="account-row__balance">{{ account().balance_minor | money: account().currency }}</span>
      @if (showChevron()) {
        <span class="account-row__chevron" aria-hidden="true">›</span>
      }
    </button>
  `,
  styles: [
    `
      .account-row {
        display: flex;
        align-items: center;
        gap: var(--mb-space-3);
        width: 100%;
        border: none;
        background: transparent;
        padding: var(--mb-space-3) 0;
        cursor: pointer;
        text-align: left;
        font-family: inherit;
        border-radius: var(--mb-radius-sm);
      }
      .account-row:hover {
        background: var(--mb-surface-muted);
      }
      .account-row__avatar {
        width: 40px;
        height: 40px;
        border-radius: 50%;
        background: var(--mb-navy-900);
        color: var(--mb-text-on-navy);
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: var(--mb-font-size-xs);
        font-weight: var(--mb-font-weight-semibold);
        flex-shrink: 0;
      }
      .account-row__info {
        display: flex;
        flex-direction: column;
        min-width: 0;
        flex: 1;
      }
      .account-row__name {
        font-size: var(--mb-font-size-sm);
        font-weight: var(--mb-font-weight-medium);
        color: var(--mb-text-primary);
      }
      .account-row__iban {
        font-size: var(--mb-font-size-xs);
        color: var(--mb-text-tertiary);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .account-row__balance {
        font-size: var(--mb-font-size-base);
        font-weight: var(--mb-font-weight-semibold);
        white-space: nowrap;
      }
      .account-row__chevron {
        color: var(--mb-text-tertiary);
        font-size: 1.1rem;
      }
    `,
  ],
})
export class AccountCard {
  readonly account = input.required<AccountRowData>();
  readonly showChevron = input(true);
  readonly opened = output<void>();
}
