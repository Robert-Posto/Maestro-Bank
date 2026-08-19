import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { forkJoin } from 'rxjs';

import { BankingService } from '../../services/banking.service';
import { TransactionsService, SpendingAnalytics } from '../../services/transactions.service';
import { BudgetsService, Budget, Subscription } from '../../services/budgets.service';
import { AccountCard, AccountRowData } from '../../shared/components/account-card/account-card';
import { TransactionRow, TransactionRowData } from '../../shared/components/transaction-row/transaction-row';
import { LoadingSkeleton } from '../../shared/components/loading-skeleton/loading-skeleton';
import { EmptyState } from '../../shared/components/empty-state/empty-state';
import { MoneyPipe } from '../../shared/pipes/money.pipe';
import { Icon } from '../../shared/components/icon/icon';
import { daysUntilBilling, daysUntilBillingLabel } from '../../shared/subscription-display';

interface QuickAction {
  label: string;
  icon: string;
  route: string;
}

const QUICK_ACTIONS: QuickAction[] = [
  { label: 'Transfer', icon: 'transfer', route: '/app/transfers' },
  { label: 'Schimb valutar', icon: 'exchange', route: '/app/exchange' },
  { label: 'Plată factură', icon: 'receipt', route: '/app/transfers' },
  { label: 'Control card', icon: 'cards', route: '/app/cards' },
];

function startOfMonthIso(): string {
  const now = new Date();
  return new Date(Date.UTC(now.getFullYear(), now.getMonth(), 1)).toISOString();
}

/**
 * Overview — vezi UI reference/Overview.png. Aerisit intenționat: fără
 * analytics complexe aici (acelea sunt în /app/spending-forecast — vezi
 * task-ul MaestroBank, secțiunea 7 & 16). Toate valorile vin din API, nu
 * sunt hardcodate din screenshot.
 */
@Component({
  selector: 'app-overview',
  standalone: true,
  imports: [RouterLink, AccountCard, TransactionRow, LoadingSkeleton, EmptyState, MoneyPipe, Icon],
  templateUrl: './overview.html',
  styleUrl: './overview.css',
})
export class Overview implements OnInit {
  protected readonly Math = Math;
  private readonly banking = inject(BankingService);
  private readonly transactionsApi = inject(TransactionsService);
  private readonly budgetsApi = inject(BudgetsService);
  private readonly router = inject(Router);

  protected readonly quickActions = QUICK_ACTIONS;
  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);

  protected readonly account = signal<AccountRowData | null>(null);
  protected readonly recentTransactions = signal<TransactionRowData[]>([]);
  protected readonly spending = signal<SpendingAnalytics | null>(null);
  protected readonly monthlyIncomeMinor = signal(0);
  protected readonly budgets = signal<Budget[]>([]);
  protected readonly upcomingSubscriptions = signal<Subscription[]>([]);

  protected readonly daysUntilBillingLabel = daysUntilBillingLabel;

  protected readonly budgetProgress = computed(() => {
    const budgetList = this.budgets().filter((b) => b.active);
    if (budgetList.length === 0) return null;

    const spendByCategory = new Map(this.spending()?.by_category.map((c) => [c.category, c.amount_minor]) ?? []);
    const totalLimit = budgetList.reduce((sum, b) => sum + b.limit_minor, 0);
    const totalSpent = budgetList.reduce((sum, b) => sum + (spendByCategory.get(b.category) ?? 0), 0);
    const percent = totalLimit > 0 ? Math.min(Math.round((totalSpent / totalLimit) * 100), 999) : 0;
    return { totalLimit, totalSpent, percent };
  });

  ngOnInit(): void {
    this.loadOverview();
  }

  private loadOverview(): void {
    this.loading.set(true);
    this.error.set(null);

    forkJoin({
      account: this.banking.getMyAccount(),
      transactions: this.banking.getTransactions(5, 0),
      incomeThisMonth: this.transactionsApi.list({ direction: 'incoming', date_from: startOfMonthIso() }, 100, 0),
      spending: this.transactionsApi.getSpendingAnalytics(),
      budgets: this.budgetsApi.listBudgets(),
      subscriptions: this.budgetsApi.listSubscriptions(),
    }).subscribe({
      next: ({ account, transactions, incomeThisMonth, spending, budgets, subscriptions }) => {
        this.account.set({
          id: account.id,
          name: 'Cont curent',
          iban: account.iban,
          currency: account.currency,
          balance_minor: account.balance_minor,
          status: account.status,
        });
        this.recentTransactions.set(transactions);
        this.monthlyIncomeMinor.set(incomeThisMonth.reduce((sum, t) => sum + t.amount_minor, 0));
        this.spending.set(spending);
        this.budgets.set(budgets);
        // Sortăm după cât de aproape e următoarea facturare, ca secțiunea
        // "Abonamente apropiate" să arate chiar cele mai urgente, nu primele 3 din listă.
        this.upcomingSubscriptions.set(
          subscriptions
            .filter((s) => s.active)
            .sort((a, b) => daysUntilBilling(a.billing_day) - daysUntilBilling(b.billing_day))
            .slice(0, 3),
        );
        this.loading.set(false);
      },
      error: () => {
        this.error.set('Nu am putut încărca datele contului. Încearcă din nou.');
        this.loading.set(false);
      },
    });
  }

  protected goTo(route: string): void {
    this.router.navigate([route]);
  }

  protected retry(): void {
    this.loadOverview();
  }
}
