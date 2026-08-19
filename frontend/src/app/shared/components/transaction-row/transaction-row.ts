import { Component, computed, input, output } from '@angular/core';
import { DatePipe } from '@angular/common';

import { MoneyPipe } from '../../pipes/money.pipe';
import { categoryLabel } from '../../categories';
import { transactionDisplayName } from '../../transaction-display';
import { MerchantAvatar } from '../merchant-avatar/merchant-avatar';

export interface TransactionRowData {
  id: string;
  direction: 'incoming' | 'outgoing';
  amount_minor: number;
  currency: string;
  counterparty_iban: string;
  counterparty_name?: string | null;
  description: string;
  category: string;
  status: string;
  created_at: string;
}

/** Rând compact de tranzacție — Overview "Tranzacții recente", Accounts. */
@Component({
  selector: 'app-transaction-row',
  standalone: true,
  imports: [MoneyPipe, DatePipe, MerchantAvatar],
  template: `
    <button type="button" class="tx-row" (click)="opened.emit()">
      <app-merchant-avatar
        [name]="displayName()"
        [description]="transaction().description"
        [isPerson]="!!transaction().counterparty_name"
        [category]="transaction().category"
      />
      <span class="tx-row__info">
        <span class="tx-row__title">{{ displayName() }}</span>
        <span class="tx-row__meta">{{ categoryLabel() }} · {{ transaction().created_at | date: 'dd MMM yyyy' }}</span>
      </span>
      <span class="tx-row__amount" [class.tx-row__amount--in]="transaction().direction === 'incoming'">
        {{ transaction().direction === 'incoming' ? '+' : '-' }}{{ transaction().amount_minor | money: transaction().currency : false }}
        {{ transaction().currency === 'RON' ? 'lei' : transaction().currency }}
      </span>
    </button>
  `,
  styles: [
    `
      .tx-row {
        display: flex;
        align-items: center;
        gap: var(--mb-space-3);
        width: 100%;
        border: none;
        background: transparent;
        padding: var(--mb-space-2) 0;
        cursor: pointer;
        text-align: left;
        font-family: inherit;
        border-radius: var(--mb-radius-sm);
      }
      .tx-row:hover {
        background: var(--mb-surface-muted);
      }
      .tx-row__info {
        display: flex;
        flex-direction: column;
        min-width: 0;
        flex: 1;
      }
      .tx-row__title {
        font-size: var(--mb-font-size-sm);
        font-weight: var(--mb-font-weight-medium);
        color: var(--mb-text-primary);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .tx-row__meta {
        font-size: var(--mb-font-size-xs);
        color: var(--mb-text-tertiary);
      }
      .tx-row__amount {
        font-size: var(--mb-font-size-sm);
        font-weight: var(--mb-font-weight-semibold);
        color: var(--mb-negative);
        white-space: nowrap;
      }
      .tx-row__amount--in {
        color: var(--mb-positive);
      }
    `,
  ],
})
export class TransactionRow {
  readonly transaction = input.required<TransactionRowData>();
  readonly opened = output<void>();

  protected readonly displayName = computed(() => transactionDisplayName(this.transaction()));
  protected readonly categoryLabel = computed(() => categoryLabel(this.transaction().category));
}
