import { Component, computed, input, output } from '@angular/core';
import { DatePipe } from '@angular/common';

import { MoneyPipe } from '../../pipes/money.pipe';
import { categoryLabel } from '../../categories';
import { transactionDisplayName } from '../../transaction-display';
import { StatusBadge } from '../status-badge/status-badge';
import { ActionButton } from '../action-button/action-button';

export interface TransactionDetail {
  id: string;
  direction: 'incoming' | 'outgoing';
  amount_minor: number;
  currency: string;
  counterparty_iban: string;
  counterparty_name?: string | null;
  description: string;
  category: string;
  status: string;
  recognized: boolean;
  reported: boolean;
  created_at: string;
}

/**
 * Panoul lateral "Detalii tranzacție" (vezi UI reference/Transactions.png).
 * Zona "Financial Guardian" e păstrată vizual, dar marcată explicit
 * "Coming in AI phase" — nu simulăm o analiză AI reală (vezi task-ul
 * MaestroBank, secțiunea 11).
 */
@Component({
  selector: 'app-transaction-details-panel',
  standalone: true,
  imports: [MoneyPipe, DatePipe, StatusBadge, ActionButton],
  templateUrl: './transaction-details-panel.html',
  styleUrl: './transaction-details-panel.css',
})
export class TransactionDetailsPanel {
  readonly transaction = input.required<TransactionDetail>();
  readonly accountLabel = input('Cont curent RON');
  readonly recognizing = input(false);
  readonly reporting = input(false);

  readonly closed = output<void>();
  readonly recognize = output<void>();
  readonly report = output<void>();
  readonly contactSupport = output<void>();

  protected readonly displayName = computed(() => transactionDisplayName(this.transaction()));
  protected readonly categoryLabel = computed(() => categoryLabel(this.transaction().category));
  protected readonly signedAmount = computed(() => (this.transaction().direction === 'outgoing' ? -1 : 1) * this.transaction().amount_minor);
}
