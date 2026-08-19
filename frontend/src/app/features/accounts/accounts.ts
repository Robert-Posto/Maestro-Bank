import { Component, OnInit, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { DatePipe } from '@angular/common';

import { AccountView, BankingService } from '../../services/banking.service';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { StatusBadge } from '../../shared/components/status-badge/status-badge';
import { LoadingSkeleton } from '../../shared/components/loading-skeleton/loading-skeleton';
import { EmptyState } from '../../shared/components/empty-state/empty-state';
import { ActionButton } from '../../shared/components/action-button/action-button';
import { Icon } from '../../shared/components/icon/icon';
import { MoneyPipe } from '../../shared/pipes/money.pipe';
import { ToastService } from '../../shared/components/toast/toast.service';

/**
 * Conturi — vezi task-ul MaestroBank, secțiunea 8. MVP-ul are un singur
 * cont curent RON per user (provizionat automat la register). Pagina e
 * pregătită pentru a afișa mai multe conturi când backendul le va oferi.
 */
@Component({
  selector: 'app-accounts',
  standalone: true,
  imports: [PageHeader, StatusBadge, LoadingSkeleton, EmptyState, ActionButton, Icon, MoneyPipe, DatePipe],
  templateUrl: './accounts.html',
  styleUrl: './accounts.css',
})
export class Accounts implements OnInit {
  private readonly banking = inject(BankingService);
  private readonly router = inject(Router);
  private readonly toast = inject(ToastService);

  protected readonly account = signal<AccountView | null>(null);
  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly copied = signal(false);

  ngOnInit(): void {
    this.load();
  }

  private load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.banking.getMyAccount().subscribe({
      next: (account) => {
        this.account.set(account);
        this.loading.set(false);
      },
      error: () => {
        this.error.set('Nu am putut încărca contul.');
        this.loading.set(false);
      },
    });
  }

  protected copyIban(): void {
    const iban = this.account()?.iban;
    if (!iban) return;
    navigator.clipboard?.writeText(iban).then(() => {
      this.copied.set(true);
      this.toast.success('IBAN copiat în clipboard.');
      setTimeout(() => this.copied.set(false), 2000);
    });
  }

  protected goToTransfer(): void {
    this.router.navigate(['/app/transfers']);
  }

  protected goToTransactions(): void {
    this.router.navigate(['/app/transactions']);
  }
}
