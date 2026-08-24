import { Component, computed, input, output } from '@angular/core';
import { DatePipe } from '@angular/common';

import { MoneyPipe } from '../../pipes/money.pipe';
import { categoryLabel } from '../../categories';
import { transactionDisplayName } from '../../transaction-display';
import { StatusBadge } from '../status-badge/status-badge';
import { ActionButton } from '../action-button/action-button';
import { Icon } from '../icon/icon';
import { MerchantAvatar } from '../merchant-avatar/merchant-avatar';

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
  hold?: { expires_at: string; resolution: string | null } | null;
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
  imports: [MoneyPipe, DatePipe, StatusBadge, ActionButton, Icon, MerchantAvatar],
  templateUrl: './transaction-details-panel.html',
  styleUrl: './transaction-details-panel.css',
})
export class TransactionDetailsPanel {
  readonly transaction = input.required<TransactionDetail>();
  readonly accountLabel = input('Cont curent RON');
  readonly recognizing = input(false);
  readonly reporting = input(false);
  readonly cancellingHold = input(false);

  readonly closed = output<void>();
  readonly recognize = output<void>();
  readonly report = output<void>();
  readonly contactSupport = output<void>();
  readonly cancelHold = output<void>();

  protected readonly isPendingReview = computed(() => this.transaction().status === 'pending_review');

  protected readonly displayName = computed(() => transactionDisplayName(this.transaction()));
  protected readonly categoryLabel = computed(() => categoryLabel(this.transaction().category));
  protected readonly signedAmount = computed(() => (this.transaction().direction === 'outgoing' ? -1 : 1) * this.transaction().amount_minor);
}
