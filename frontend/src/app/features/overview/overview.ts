import { Component, OnInit, WritableSignal, computed, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { forkJoin } from 'rxjs';

import { BankingService } from '../../services/banking.service';
import { LanguageService } from '../../services/language.service';
import { TransactionsService, SpendingAnalytics } from '../../services/transactions.service';
import { BudgetsService, Budget, Subscription } from '../../services/budgets.service';
import { AccountCard, AccountRowData } from '../../shared/components/account-card/account-card';
import { TransactionRow, TransactionRowData } from '../../shared/components/transaction-row/transaction-row';
import { LoadingSkeleton } from '../../shared/components/loading-skeleton/loading-skeleton';
import { EmptyState } from '../../shared/components/empty-state/empty-state';
import { MoneyPipe } from '../../shared/pipes/money.pipe';
import { Icon } from '../../shared/components/icon/icon';
import { TranslatePipe } from '../../shared/pipes/translate.pipe';
import { daysUntilBilling, daysUntilBillingLabel } from '../../shared/subscription-display';

interface QuickAction {
  label: string;
  icon: string;
  route: string;
  queryParams?: Record<string, string>;
}

const QUICK_ACTIONS: QuickAction[] = [
  { label: 'overview.action.transfer', icon: 'transfer', route: '/app/transfers' },
  { label: 'overview.action.exchange', icon: 'exchange', route: '/app/exchange' },
  // Aceeași pagină ca "Transfer", dar cu categoria presetată pe "bills" —
  // altfel cele 2 tile-uri ar duce spre exact aceeași destinație, fără
  // nicio diferență vizibilă pentru user (duplicare confuză).
  { label: 'overview.action.payBill', icon: 'receipt', route: '/app/transfers', queryParams: { category: 'bills' } },
  { label: 'overview.action.cardControls', icon: 'cards', route: '/app/cards' },
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
  imports: [RouterLink, AccountCard, TransactionRow, LoadingSkeleton, EmptyState, MoneyPipe, Icon, TranslatePipe],
  templateUrl: './overview.html',
  styleUrl: './overview.css',
})
export class Overview implements OnInit {
  protected readonly Math = Math;
  private readonly banking = inject(BankingService);
  private readonly transactionsApi = inject(TransactionsService);
  private readonly budgetsApi = inject(BudgetsService);
  private readonly router = inject(Router);
  private readonly language = inject(LanguageService);

  protected readonly quickActions = QUICK_ACTIONS;
  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);

  protected readonly account = signal<AccountRowData | null>(null);
  protected readonly recentTransactions = signal<TransactionRowData[]>([]);
  protected readonly spending = signal<SpendingAnalytics | null>(null);
  protected readonly monthlyIncomeMinor = signal(0);
  protected readonly budgets = signal<Budget[]>([]);
  protected readonly upcomingSubscriptions = signal<Subscription[]>([]);

  // Valori "animate" pentru stat-card-urile de sus — pornesc de la 0 și
  // urcă spre valoarea reală la fiecare încărcare (count-up), independent
  // de valoarea propriu-zisă folosită restul aplicației.
  protected readonly balanceDisplayMinor = signal(0);
  protected readonly spendingDisplayMinor = signal(0);
  protected readonly incomeDisplayMinor = signal(0);
  protected readonly progressDisplayPercent = signal(0);

  protected daysUntilBillingLabel(billingDay: number): string {
    return daysUntilBillingLabel(billingDay, this.language.language());
  }

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
          // Cheie de traducere, NU string deja tradus — AccountCard aplică
          // `| translate` la afișare, deci rămâne reactiv la comutarea de
          // limbă chiar și după ce datele au fost încărcate o singură dată.
          name: 'overview.currentAccount',
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

        this.animateTo(this.balanceDisplayMinor, account.balance_minor);
        this.animateTo(this.spendingDisplayMinor, spending?.total_spent_minor ?? 0);
        this.animateTo(this.incomeDisplayMinor, this.monthlyIncomeMinor());
        this.animateTo(this.progressDisplayPercent, this.budgetProgress()?.percent ?? 0);
      },
      error: () => {
        this.error.set(this.language.t('overview.loadError'));
        this.loading.set(false);
      },
    });
  }

  protected goTo(route: string): void {
    this.router.navigate([route]);
  }

  protected goToQuickAction(action: QuickAction): void {
    this.router.navigate([action.route], action.queryParams ? { queryParams: action.queryParams } : {});
  }

  protected retry(): void {
    this.loadOverview();
  }

  /** Anima o valoare întreagă de la 0 spre `target` (ease-out) — folosit doar pentru count-up-ul stat-card-urilor. */
  private animateTo(target: WritableSignal<number>, value: number, durationMs = 600): void {
    const start = performance.now();
    const step = (now: number) => {
      const t = Math.min((now - start) / durationMs, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      target.set(Math.round(value * eased));
      if (t < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }
}
