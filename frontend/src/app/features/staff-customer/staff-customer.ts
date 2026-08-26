import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { forkJoin } from 'rxjs';

import { AccountView, TransactionView } from '../../services/banking.service';
import { StaffService } from '../../services/staff.service';
import { ACCOUNT_TYPE_CATALOG } from '../../shared/account-types';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { LoadingSkeleton } from '../../shared/components/loading-skeleton/loading-skeleton';
import { EmptyState } from '../../shared/components/empty-state/empty-state';
import { ActionButton } from '../../shared/components/action-button/action-button';
import { Icon } from '../../shared/components/icon/icon';
import { AccountCard, AccountRowData } from '../../shared/components/account-card/account-card';
import { TransactionRow, TransactionRowData } from '../../shared/components/transaction-row/transaction-row';
import { TransactionDetailsPanel, TransactionDetail } from '../../shared/components/transaction-details-panel/transaction-details-panel';
import { extractErrorMessage } from '../../shared/error-utils';

/**
 * Personal — vedere READ-ONLY a conturilor + tranzacțiilor unui client
 * oarecare, deschisă din staff-holds ("Vezi contul clientului"). Nicio
 * acțiune de scriere aici (fără transfer, fără editare) — vezi
 * StaffService.getCustomerAccounts/getCustomerTransactions, gatate server-side
 * de RequireStaff pe ambele servicii (accounts + transactions).
 */
@Component({
  selector: 'app-staff-customer',
  standalone: true,
  imports: [PageHeader, LoadingSkeleton, EmptyState, ActionButton, Icon, AccountCard, TransactionRow, TransactionDetailsPanel],
  templateUrl: './staff-customer.html',
  styleUrl: './staff-customer.css',
})
export class StaffCustomer implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly staffApi = inject(StaffService);

  protected readonly userId = this.route.snapshot.paramMap.get('userId') ?? '';

  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly accounts = signal<AccountView[]>([]);
  protected readonly transactions = signal<TransactionView[]>([]);

  protected readonly accountRows = computed<AccountRowData[]>(() =>
    this.accounts().map((account) => ({
      id: account.id,
      name: ACCOUNT_TYPE_CATALOG[account.account_type]?.label ?? account.account_type,
      iban: account.iban,
      currency: account.currency,
      balance_minor: account.balance_minor,
      status: account.status,
    })),
  );

  protected readonly transactionRows = computed<TransactionRowData[]>(() => this.transactions());

  /** Tranzacția deschisă în modalul de detalii (read-only) — vezi openDetails. */
  protected readonly selectedTransaction = signal<TransactionDetail | null>(null);

  ngOnInit(): void {
    if (!this.userId) {
      this.error.set('Lipsește identificatorul clientului.');
      this.loading.set(false);
      return;
    }
    this.load();
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    forkJoin({
      accounts: this.staffApi.getCustomerAccounts(this.userId),
      transactions: this.staffApi.getCustomerTransactions(this.userId, 25),
    }).subscribe({
      next: ({ accounts, transactions }) => {
        this.accounts.set(accounts);
        this.transactions.set(transactions);
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set(extractErrorMessage(err, 'Nu am putut încărca datele clientului.'));
        this.loading.set(false);
      },
    });
  }

  protected back(): void {
    this.router.navigate(['/admin/holds']);
  }

  protected openDetails(transactionId: string): void {
    const tx = this.transactions().find((t) => t.id === transactionId) ?? null;
    this.selectedTransaction.set(tx);
  }

  protected closeDetails(): void {
    this.selectedTransaction.set(null);
  }
}
