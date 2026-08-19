import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { forkJoin } from 'rxjs';

import { Budget, BudgetPeriod, BudgetsService, Subscription } from '../../services/budgets.service';
import { SpendingAnalytics, TransactionsService } from '../../services/transactions.service';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { ActionButton } from '../../shared/components/action-button/action-button';
import { Icon } from '../../shared/components/icon/icon';
import { MoneyPipe } from '../../shared/pipes/money.pipe';
import { EmptyState } from '../../shared/components/empty-state/empty-state';
import { LoadingSkeleton } from '../../shared/components/loading-skeleton/loading-skeleton';
import { Modal } from '../../shared/components/modal/modal';
import { ConfirmDialog } from '../../shared/components/confirm-dialog/confirm-dialog';
import { TRANSACTION_CATEGORIES, categoryColorVar, categoryLabel } from '../../shared/categories';
import { ToastService } from '../../shared/components/toast/toast.service';
import { extractErrorMessage } from '../../shared/error-utils';
import { daysRemainingLabel, daysUntilBilling, daysUntilBillingLabel } from '../../shared/subscription-display';
import { MerchantAvatar } from '../../shared/components/merchant-avatar/merchant-avatar';

type Tab = 'budgets' | 'subscriptions';

interface BudgetWithProgress extends Budget {
  spentMinor: number;
  progressPercent: number;
}

interface BudgetsSummary {
  totalLimitMinor: number;
  totalSpentMinor: number;
  percent: number;
  activeCount: number;
}

interface SubscriptionsSummary {
  totalMonthlyMinor: number;
  activeCount: number;
  nextDays: number | null;
  nextName: string | null;
}

/** Bugete + abonamente — vezi task-ul MaestroBank, secțiunile 18 și 19. */
@Component({
  selector: 'app-budgets',
  standalone: true,
  imports: [FormsModule, PageHeader, ActionButton, Icon, MoneyPipe, EmptyState, LoadingSkeleton, Modal, ConfirmDialog, MerchantAvatar],
  templateUrl: './budgets.html',
  styleUrl: './budgets.css',
})
export class Budgets implements OnInit {
  private readonly budgetsApi = inject(BudgetsService);
  private readonly transactionsApi = inject(TransactionsService);
  private readonly toast = inject(ToastService);

  protected readonly categories = TRANSACTION_CATEGORIES;
  protected readonly categoryLabel = categoryLabel;
  protected readonly categoryColorVar = categoryColorVar;
  protected readonly daysUntilBilling = daysUntilBilling;
  protected readonly daysUntilBillingLabel = daysUntilBillingLabel;
  protected readonly daysRemainingLabel = daysRemainingLabel;
  protected readonly tab = signal<Tab>('budgets');

  protected readonly loading = signal(true);
  protected readonly budgets = signal<Budget[]>([]);
  protected readonly subscriptions = signal<Subscription[]>([]);
  protected readonly spending = signal<SpendingAnalytics | null>(null);

  protected readonly budgetsWithProgress = computed<BudgetWithProgress[]>(() => {
    const spendByCategory = new Map(this.spending()?.by_category.map((c) => [c.category, c.amount_minor]) ?? []);
    return this.budgets().map((b) => {
      const spentMinor = spendByCategory.get(b.category) ?? 0;
      const progressPercent = b.limit_minor > 0 ? Math.min(Math.round((spentMinor / b.limit_minor) * 100), 999) : 0;
      return { ...b, spentMinor, progressPercent };
    });
  });

  protected readonly budgetsSummary = computed<BudgetsSummary>(() => {
    const active = this.budgetsWithProgress().filter((b) => b.active);
    const totalLimitMinor = active.reduce((sum, b) => sum + b.limit_minor, 0);
    const totalSpentMinor = active.reduce((sum, b) => sum + b.spentMinor, 0);
    const percent = totalLimitMinor > 0 ? Math.min(Math.round((totalSpentMinor / totalLimitMinor) * 100), 999) : 0;
    return { totalLimitMinor, totalSpentMinor, percent, activeCount: active.length };
  });

  protected readonly subscriptionsSummary = computed<SubscriptionsSummary>(() => {
    const active = this.subscriptions().filter((s) => s.active);
    const totalMonthlyMinor = active.reduce((sum, s) => sum + s.amount_minor, 0);
    let nextDays: number | null = null;
    let nextName: string | null = null;
    for (const s of active) {
      const days = daysUntilBilling(s.billing_day);
      if (nextDays === null || days < nextDays) {
        nextDays = days;
        nextName = s.name;
      }
    }
    return { totalMonthlyMinor, activeCount: active.length, nextDays, nextName };
  });

  // --- Budget form ---
  protected readonly budgetModalOpen = signal(false);
  protected readonly budgetSaving = signal(false);
  protected readonly budgetName = signal('');
  protected readonly budgetCategory = signal('other');
  protected readonly budgetLimit = signal<number | null>(null);
  protected readonly budgetPeriod = signal<BudgetPeriod>('monthly');
  protected readonly pendingDeleteBudget = signal<Budget | null>(null);

  // --- Subscription form ---
  protected readonly subscriptionModalOpen = signal(false);
  protected readonly subscriptionSaving = signal(false);
  protected readonly subscriptionName = signal('');
  protected readonly subscriptionAmount = signal<number | null>(null);
  protected readonly subscriptionDay = signal(1);
  protected readonly pendingDeleteSubscription = signal<Subscription | null>(null);

  ngOnInit(): void {
    this.load();
  }

  private load(): void {
    this.loading.set(true);
    forkJoin({
      budgets: this.budgetsApi.listBudgets(),
      subscriptions: this.budgetsApi.listSubscriptions(),
      spending: this.transactionsApi.getSpendingAnalytics(),
    }).subscribe({
      next: ({ budgets, subscriptions, spending }) => {
        this.budgets.set(budgets);
        this.subscriptions.set(subscriptions);
        this.spending.set(spending);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  /** "urgent" (≤3 zile), "soon" (≤7 zile) sau "" — pentru accentul vizual al badge-ului de scadență. */
  protected billingUrgency(billingDay: number): 'urgent' | 'soon' | '' {
    const days = daysUntilBilling(billingDay);
    if (days <= 3) return 'urgent';
    if (days <= 7) return 'soon';
    return '';
  }

  // --- Budgets CRUD ---

  protected openBudgetModal(): void {
    this.budgetName.set('');
    this.budgetCategory.set('other');
    this.budgetLimit.set(null);
    this.budgetPeriod.set('monthly');
    this.budgetModalOpen.set(true);
  }

  protected saveBudget(): void {
    if (!this.budgetName().trim() || !this.budgetLimit() || this.budgetLimit()! <= 0) {
      this.toast.error('Completează numele și o limită validă.');
      return;
    }
    this.budgetSaving.set(true);
    this.budgetsApi
      .createBudget({
        name: this.budgetName().trim(),
        category: this.budgetCategory(),
        limit_minor: Math.round(this.budgetLimit()! * 100),
        period: this.budgetPeriod(),
      })
      .subscribe({
        next: (budget) => {
          this.budgets.update((list) => [budget, ...list]);
          this.budgetSaving.set(false);
          this.budgetModalOpen.set(false);
          this.toast.success('Buget creat.');
        },
        error: (err) => {
          this.budgetSaving.set(false);
          this.toast.error(extractErrorMessage(err, 'Nu am putut crea bugetul.'));
        },
      });
  }

  protected toggleBudgetActive(budget: Budget): void {
    this.budgetsApi.updateBudget(budget.id, { active: !budget.active }).subscribe({
      next: (updated) => this.budgets.update((list) => list.map((b) => (b.id === updated.id ? updated : b))),
      error: (err) => this.toast.error(extractErrorMessage(err, 'Nu am putut actualiza bugetul.')),
    });
  }

  protected confirmDeleteBudget(): void {
    const budget = this.pendingDeleteBudget();
    if (!budget) return;
    this.budgetsApi.deleteBudget(budget.id).subscribe({
      next: () => {
        this.budgets.update((list) => list.filter((b) => b.id !== budget.id));
        this.pendingDeleteBudget.set(null);
        this.toast.success('Buget șters.');
      },
      error: (err) => {
        this.pendingDeleteBudget.set(null);
        this.toast.error(extractErrorMessage(err, 'Nu am putut șterge bugetul.'));
      },
    });
  }

  // --- Subscriptions CRUD ---

  protected openSubscriptionModal(): void {
    this.subscriptionName.set('');
    this.subscriptionAmount.set(null);
    this.subscriptionDay.set(1);
    this.subscriptionModalOpen.set(true);
  }

  protected saveSubscription(): void {
    if (!this.subscriptionName().trim() || !this.subscriptionAmount() || this.subscriptionAmount()! <= 0) {
      this.toast.error('Completează numele și o sumă validă.');
      return;
    }
    this.subscriptionSaving.set(true);
    this.budgetsApi
      .createSubscription({
        name: this.subscriptionName().trim(),
        amount_minor: Math.round(this.subscriptionAmount()! * 100),
        billing_day: this.subscriptionDay(),
      })
      .subscribe({
        next: (sub) => {
          this.subscriptions.update((list) => [sub, ...list]);
          this.subscriptionSaving.set(false);
          this.subscriptionModalOpen.set(false);
          this.toast.success('Abonament creat.');
        },
        error: (err) => {
          this.subscriptionSaving.set(false);
          this.toast.error(extractErrorMessage(err, 'Nu am putut crea abonamentul.'));
        },
      });
  }

  protected toggleSubscriptionActive(sub: Subscription): void {
    this.budgetsApi.updateSubscription(sub.id, { active: !sub.active }).subscribe({
      next: (updated) => this.subscriptions.update((list) => list.map((s) => (s.id === updated.id ? updated : s))),
      error: (err) => this.toast.error(extractErrorMessage(err, 'Nu am putut actualiza abonamentul.')),
    });
  }

  protected confirmDeleteSubscription(): void {
    const sub = this.pendingDeleteSubscription();
    if (!sub) return;
    this.budgetsApi.deleteSubscription(sub.id).subscribe({
      next: () => {
        this.subscriptions.update((list) => list.filter((s) => s.id !== sub.id));
        this.pendingDeleteSubscription.set(null);
        this.toast.success('Abonament șters.');
      },
      error: (err) => {
        this.pendingDeleteSubscription.set(null);
        this.toast.error(extractErrorMessage(err, 'Nu am putut șterge abonamentul.'));
      },
    });
  }
}
