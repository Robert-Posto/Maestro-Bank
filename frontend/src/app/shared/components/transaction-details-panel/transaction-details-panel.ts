import { Component, computed, input, output } from '@angular/core';
import { DatePipe } from '@angular/common';

import { MoneyPipe } from '../../pipes/money.pipe';
import { categoryLabel } from '../../categories';
import { transactionDisplayName } from '../../transaction-display';
import { StatusBadge, type BadgeTone } from '../status-badge/status-badge';
import { ActionButton } from '../action-button/action-button';
import { Icon } from '../icon/icon';
import { MerchantAvatar } from '../merchant-avatar/merchant-avatar';
import type { TransactionRisk } from '../../../services/banking.service';

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
  risk?: TransactionRisk | null;
  /** Screening determinist al descrierii — vezi app/content_screening.py,
   * SEPARAT de `risk` (motorul de fraudă). */
  content_warning?: string | null;
}

const RISK_TONE: Record<TransactionRisk['tier'], BadgeTone> = {
  safe: 'success',
  unusual: 'warning',
  potentially_dangerous: 'error',
  held: 'error',
};

const RISK_LABEL: Record<TransactionRisk['tier'], string> = {
  safe: 'Sigur',
  unusual: 'Neobișnuit',
  potentially_dangerous: 'Potențial riscant',
  held: 'Reținut',
};

/**
 * Panoul lateral "Detalii tranzacție" (vezi UI reference/Transactions.png).
 * Zona "Financial Guardian" arată evaluarea REALĂ de risc (vezi
 * app/guardian/ din backend) — tier + frază, niciodată ID-uri de regulă
 * sau alte detalii care ar putea "învăța" pragurile motorului.
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
  /** Vedere READ-ONLY (personal, în staff-customer — vezi task-ul) — ascunde
   * acțiunile de scriere (anulare hold, recunoaște, raportează) și CTA-ul
   * de contact suport, care n-au sens pe contul altui user. */
  readonly readonly = input(false);

  readonly closed = output<void>();
  readonly recognize = output<void>();
  readonly report = output<void>();
  readonly contactSupport = output<void>();
  readonly cancelHold = output<void>();

  protected readonly isPendingReview = computed(() => this.transaction().status === 'pending_review');

  protected readonly displayName = computed(() => transactionDisplayName(this.transaction()));
  protected readonly categoryLabel = computed(() => categoryLabel(this.transaction().category));
  protected readonly signedAmount = computed(() => (this.transaction().direction === 'outgoing' ? -1 : 1) * this.transaction().amount_minor);

  protected readonly riskTone = computed<BadgeTone>(() => {
    const risk = this.transaction().risk;
    return risk ? RISK_TONE[risk.tier] : 'neutral';
  });
  protected readonly riskLabel = computed(() => {
    const risk = this.transaction().risk;
    return risk ? RISK_LABEL[risk.tier] : '';
  });
}
