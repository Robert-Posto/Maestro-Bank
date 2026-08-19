import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { forkJoin } from 'rxjs';

import { AccountView, BankingService, CardView } from '../../services/banking.service';
import { TransactionsService, SpendingAnalytics } from '../../services/transactions.service';
import { AuthService } from '../../services/auth.service';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { StatusBadge } from '../../shared/components/status-badge/status-badge';
import { ToggleControl } from '../../shared/components/toggle-control/toggle-control';
import { LoadingSkeleton } from '../../shared/components/loading-skeleton/loading-skeleton';
import { EmptyState } from '../../shared/components/empty-state/empty-state';
import { TransactionRow, TransactionRowData } from '../../shared/components/transaction-row/transaction-row';
import { MoneyPipe } from '../../shared/pipes/money.pipe';
import { Icon } from '../../shared/components/icon/icon';
import { ToastService } from '../../shared/components/toast/toast.service';
import { extractErrorMessage } from '../../shared/error-utils';

type ToggleKey = 'online_payments_enabled' | 'contactless_enabled' | 'atm_withdrawals_enabled' | 'international_payments_enabled';

/**
 * Cardul meu — vezi UI reference/Cards.png și task-ul MaestroBank,
 * secțiunea 9. NU generăm PAN/CVV reale — doar ultimele 4 cifre demo.
 * Card controls sunt reale (accounts-service), userul poate modifica
 * DOAR propriile carduri (identitate din JWT — vezi backend).
 */
@Component({
  selector: 'app-cards',
  standalone: true,
  imports: [PageHeader, StatusBadge, ToggleControl, LoadingSkeleton, EmptyState, TransactionRow, MoneyPipe, Icon, FormsModule],
  templateUrl: './cards.html',
  styleUrl: './cards.css',
})
export class Cards implements OnInit {
  private readonly banking = inject(BankingService);
  private readonly transactionsApi = inject(TransactionsService);
  private readonly auth = inject(AuthService);
  private readonly toast = inject(ToastService);

  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);

  protected readonly account = signal<AccountView | null>(null);
  protected readonly card = signal<CardView | null>(null);
  protected readonly spending = signal<SpendingAnalytics | null>(null);
  protected readonly recentTransactions = signal<TransactionRowData[]>([]);

  protected readonly freezeBusy = signal(false);
  protected readonly settingsBusy = signal<ToggleKey | null>(null);
  protected readonly limitBusy = signal(false);
  protected readonly limitInput = signal(0);
  protected readonly editingLimit = signal(false);

  protected readonly cardholderName = computed(() => {
    const user = this.auth.currentUser();
    return user ? `${user.first_name} ${user.last_name}`.toUpperCase() : '';
  });

  ngOnInit(): void {
    this.load();
  }

  private load(): void {
    this.loading.set(true);
    this.error.set(null);

    forkJoin({
      account: this.banking.getMyAccount(),
      cards: this.banking.getMyCards(),
      spending: this.transactionsApi.getSpendingAnalytics(),
      transactions: this.banking.getTransactions(4, 0),
    }).subscribe({
      next: ({ account, cards, spending, transactions }) => {
        this.account.set(account);
        const primaryCard = cards[0] ?? null;
        this.card.set(primaryCard);
        if (primaryCard) {
          this.limitInput.set(primaryCard.daily_limit_minor / 100);
        }
        this.spending.set(spending);
        this.recentTransactions.set(transactions);
        this.loading.set(false);
      },
      error: () => {
        this.error.set('Nu am putut încărca datele cardului.');
        this.loading.set(false);
      },
    });
  }

  protected toggleFreeze(): void {
    const current = this.card();
    if (!current) return;

    this.freezeBusy.set(true);
    const request = current.is_frozen ? this.banking.unfreezeCard(current.id) : this.banking.freezeCard(current.id);
    request.subscribe({
      next: (updated) => {
        this.card.set(updated);
        this.freezeBusy.set(false);
        this.toast.success(updated.is_frozen ? 'Card blocat temporar.' : 'Card deblocat.');
      },
      error: (err) => {
        this.freezeBusy.set(false);
        this.toast.error(extractErrorMessage(err, 'Nu am putut actualiza statusul cardului.'));
      },
    });
  }

  protected toggleSetting(key: ToggleKey, value: boolean): void {
    const current = this.card();
    if (!current) return;

    this.settingsBusy.set(key);
    this.banking.updateCardSettings(current.id, { [key]: value }).subscribe({
      next: (updated) => {
        this.card.set(updated);
        this.settingsBusy.set(null);
        this.toast.success('Setările cardului au fost actualizate.');
      },
      error: (err) => {
        this.settingsBusy.set(null);
        this.toast.error(extractErrorMessage(err, 'Nu am putut actualiza setarea.'));
      },
    });
  }

  protected saveLimit(): void {
    const current = this.card();
    if (!current) return;
    const minor = Math.round(this.limitInput() * 100);
    if (minor <= 0) {
      this.toast.error('Introdu o limită validă.');
      return;
    }

    this.limitBusy.set(true);
    this.banking.updateCardLimit(current.id, minor).subscribe({
      next: (updated) => {
        this.card.set(updated);
        this.limitBusy.set(false);
        this.editingLimit.set(false);
        this.toast.success('Limita zilnică a fost actualizată.');
      },
      error: (err) => {
        this.limitBusy.set(false);
        this.toast.error(extractErrorMessage(err, 'Nu am putut actualiza limita.'));
      },
    });
  }
}
