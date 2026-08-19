import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';

import { AccountView, BankingService, Beneficiary, TransactionView } from '../../services/banking.service';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { ActionButton } from '../../shared/components/action-button/action-button';
import { Icon } from '../../shared/components/icon/icon';
import { MoneyPipe } from '../../shared/pipes/money.pipe';
import { TRANSACTION_CATEGORIES, categoryLabel } from '../../shared/categories';
import { ToastService } from '../../shared/components/toast/toast.service';

type TransferStep = 'form' | 'review' | 'success';

/**
 * Plăți & Transferuri — vezi task-ul MaestroBank, secțiunea 13.
 * Flow: From account -> Destination IBAN -> Amount -> Description ->
 * Continue -> Review -> Confirm -> Success. Backendul există deja
 * (transactions-service) — doar îl conectăm; după transfer reîmprospătăm
 * sold + tranzacții recente.
 */
@Component({
  selector: 'app-transfers',
  standalone: true,
  imports: [FormsModule, RouterLink, PageHeader, ActionButton, Icon, MoneyPipe],
  templateUrl: './transfers.html',
  styleUrl: './transfers.css',
})
export class Transfers implements OnInit {
  private readonly banking = inject(BankingService);
  private readonly toast = inject(ToastService);

  protected readonly categories = TRANSACTION_CATEGORIES;
  protected readonly categoryLabel = categoryLabel;
  protected readonly step = signal<TransferStep>('form');

  protected readonly account = signal<AccountView | null>(null);
  protected readonly beneficiaries = signal<Beneficiary[]>([]);
  protected readonly loadingContext = signal(true);

  protected readonly toIban = signal('');
  protected readonly amount = signal<number | null>(null);
  protected readonly description = signal('');
  protected readonly category = signal('other');
  protected readonly saveBeneficiaryName = signal('');
  protected readonly saveAsBeneficiary = signal(false);

  protected readonly submitting = signal(false);
  protected readonly formError = signal<string | null>(null);
  protected readonly completedTransaction = signal<TransactionView | null>(null);

  protected readonly amountMinor = computed(() => Math.round((this.amount() ?? 0) * 100));

  ngOnInit(): void {
    this.loadingContext.set(true);
    this.banking.getMyAccount().subscribe({
      next: (account) => {
        this.account.set(account);
        this.loadingContext.set(false);
      },
      error: () => this.loadingContext.set(false),
    });
    this.banking.getBeneficiaries().subscribe({ next: (list) => this.beneficiaries.set(list) });
  }

  protected selectBeneficiary(beneficiary: Beneficiary): void {
    this.toIban.set(beneficiary.iban);
  }

  protected initials(name: string): string {
    const parts = name.trim().split(/\s+/).filter(Boolean);
    if (parts.length === 0) return '?';
    return (parts[0].charAt(0) + (parts[1]?.charAt(0) ?? '')).toUpperCase();
  }

  protected goToReview(): void {
    this.formError.set(null);

    const iban = this.toIban().trim().toUpperCase().replace(/\s+/g, '');
    if (iban.length < 10) {
      this.formError.set('IBAN destinație invalid.');
      return;
    }
    if (this.account() && iban === this.account()!.iban) {
      this.formError.set('Nu poți transfera către propriul cont.');
      return;
    }
    if (!this.amount() || this.amount()! <= 0) {
      this.formError.set('Introdu o sumă validă, mai mare decât 0.');
      return;
    }
    if (this.account() && this.amountMinor() > this.account()!.balance_minor) {
      this.formError.set('Sold insuficient pentru această sumă.');
      return;
    }

    this.toIban.set(iban);
    this.step.set('review');
  }

  protected backToForm(): void {
    this.step.set('form');
  }

  protected confirmTransfer(): void {
    this.submitting.set(true);
    this.formError.set(null);

    this.banking
      .createTransfer({
        to_iban: this.toIban(),
        amount_minor: this.amountMinor(),
        description: this.description().trim(),
        category: this.category(),
      })
      .subscribe({
        next: (transaction) => {
          this.submitting.set(false);
          this.completedTransaction.set(transaction);
          this.step.set('success');
          this.toast.success('Transfer efectuat cu succes.');
          this.refreshAccount();
          this.maybeSaveBeneficiary();
        },
        error: (err) => {
          this.submitting.set(false);
          this.formError.set(this.mapTransferError(err));
          this.step.set('form');
        },
      });
  }

  private maybeSaveBeneficiary(): void {
    if (!this.saveAsBeneficiary() || !this.saveBeneficiaryName().trim()) return;
    this.banking.createBeneficiary(this.saveBeneficiaryName().trim(), this.toIban()).subscribe({
      next: (beneficiary) => this.beneficiaries.update((list) => [beneficiary, ...list]),
    });
  }

  private refreshAccount(): void {
    this.banking.getMyAccount().subscribe({ next: (account) => this.account.set(account) });
  }

  private mapTransferError(err: unknown): string {
    if (err instanceof HttpErrorResponse) {
      if (err.status === 0) return 'Serviciul de transferuri este indisponibil momentan. Încearcă din nou.';
      if (err.status === 409) return 'Sold insuficient pentru acest transfer.';
      if (err.status === 404) return 'Contul destinație (IBAN) nu există.';
      if (err.status === 400) {
        const detail = err.error?.detail;
        if (typeof detail === 'string') return detail;
      }
    }
    return 'Transferul a eșuat. Verifică datele și încearcă din nou.';
  }

  protected startNewTransfer(): void {
    this.toIban.set('');
    this.amount.set(null);
    this.description.set('');
    this.category.set('other');
    this.saveAsBeneficiary.set(false);
    this.saveBeneficiaryName.set('');
    this.completedTransaction.set(null);
    this.step.set('form');
  }
}
