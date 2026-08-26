import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { DatePipe, LowerCasePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { AccountType, AccountView, BankingService, CreatableAccountType, PocketView } from '../../services/banking.service';
import { TransactionsService } from '../../services/transactions.service';
import { ACCOUNT_TYPE_CATALOG, CREATABLE_ACCOUNT_TYPES } from '../../shared/account-types';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { StatusBadge } from '../../shared/components/status-badge/status-badge';
import { LoadingSkeleton } from '../../shared/components/loading-skeleton/loading-skeleton';
import { EmptyState } from '../../shared/components/empty-state/empty-state';
import { ActionButton } from '../../shared/components/action-button/action-button';
import { Icon } from '../../shared/components/icon/icon';
import { MoneyPipe } from '../../shared/pipes/money.pipe';
import { Modal } from '../../shared/components/modal/modal';
import { ConfirmDialog } from '../../shared/components/confirm-dialog/confirm-dialog';
import { AccountCreateEvent, AccountTypeCarousel } from '../../shared/components/account-type-carousel/account-type-carousel';
import { ToastService } from '../../shared/components/toast/toast.service';
import { extractErrorMessage } from '../../shared/error-utils';

type Tab = 'accounts' | 'pockets';

/**
 * Conturi — vezi task-ul MaestroBank, secțiunea 8, extins cu deschiderea
 * de conturi suplimentare (economii/depozit/student — accounts-service
 * POST /accounts/new). Contul curent rămâne SINGURUL cont sursă pentru
 * transferuri (vezi accounts-service::get_account_for_user) — conturile
 * noi se alimentează prin Transferuri, folosind IBAN-ul lor propriu.
 *
 * Extinsă și cu Pockets (obiective de economisire, în interiorul
 * contului curent RON) — vezi secțiunea dedicată mai jos, complet
 * separată de fluxul de conturi multiple (nume distincte pentru modale,
 * ca să nu se suprapună cu cel de deschidere cont nou).
 */
@Component({
  selector: 'app-accounts',
  standalone: true,
  imports: [
    PageHeader,
    StatusBadge,
    LoadingSkeleton,
    EmptyState,
    ActionButton,
    Icon,
    MoneyPipe,
    DatePipe,
    FormsModule,
    LowerCasePipe,
    Modal,
    ConfirmDialog,
    AccountTypeCarousel,
  ],
  templateUrl: './accounts.html',
  styleUrl: './accounts.css',
})
export class Accounts implements OnInit {
  private readonly banking = inject(BankingService);
  private readonly transactionsApi = inject(TransactionsService);
  private readonly router = inject(Router);
  private readonly toast = inject(ToastService);

  protected readonly catalog = ACCOUNT_TYPE_CATALOG;
  /** "current" + toate tipurile creabile — vezi accounts-service::_MAX_ACCOUNTS_PER_USER (aceeași sursă de adevăr). */
  protected readonly maxAccounts = 1 + CREATABLE_ACCOUNT_TYPES.length;

  protected readonly tab = signal<Tab>('accounts');

  protected readonly accounts = signal<AccountView[]>([]);
  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly copiedId = signal<string | null>(null);

  protected readonly createModalOpen = signal(false);
  protected readonly creatingType = signal<AccountType | null>(null);

  protected readonly pendingDeleteAccount = signal<AccountView | null>(null);
  protected readonly deleting = signal(false);

  // --- Extras de cont (PDF) — orice cont, nu doar cel curent -------------
  protected readonly statementAccount = signal<AccountView | null>(null);
  protected readonly statementFrom = signal(this.monthStartIso());
  protected readonly statementTo = signal(this.todayIso());
  protected readonly generatingStatement = signal(false);

  protected readonly availableTypes = computed(() => {
    const owned = new Set(this.accounts().map((a) => a.account_type));
    return CREATABLE_ACCOUNT_TYPES.filter((t) => !owned.has(t)).map((t) => this.catalog[t]);
  });

  protected readonly totalBalanceMinor = computed(() => this.accounts().reduce((sum, a) => sum + a.balance_minor, 0));
  protected readonly currentAccount = computed(() => this.accounts().find((a) => a.account_type === 'current') ?? null);
  protected readonly setAsideMinor = computed(() =>
    this.accounts()
      .filter((a) => a.account_type === 'savings' || a.account_type === 'deposit')
      .reduce((sum, a) => sum + a.balance_minor, 0),
  );

  // --- Pockets (obiective de economisire, în contul curent) ---------------
  protected readonly pockets = signal<PocketView[]>([]);
  protected readonly pocketsLoading = signal(true);
  protected readonly totalAllocatedMinor = computed(() => this.pockets().reduce((sum, p) => sum + p.saved_minor, 0));

  protected readonly pocketCreateModalOpen = signal(false);
  protected readonly newPocketName = signal('');
  protected readonly newPocketTargetRon = signal(500);
  protected readonly creatingPocket = signal(false);

  protected readonly depositModalPocket = signal<PocketView | null>(null);
  protected readonly depositAmountRon = signal(50);
  protected readonly depositBusy = signal(false);

  ngOnInit(): void {
    this.load();
    this.loadPockets();
  }

  private load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.banking.getAllAccounts().subscribe({
      next: (accounts) => {
        this.accounts.set(accounts);
        this.loading.set(false);
      },
      error: () => {
        this.error.set('Nu am putut încărca conturile.');
        this.loading.set(false);
      },
    });
  }

  private loadPockets(): void {
    this.pocketsLoading.set(true);
    this.banking.getPockets().subscribe({
      next: (pockets) => {
        this.pockets.set(pockets);
        this.pocketsLoading.set(false);
      },
      error: () => this.pocketsLoading.set(false),
    });
  }

  protected openPocketCreateModal(): void {
    this.newPocketName.set('');
    this.newPocketTargetRon.set(500);
    this.pocketCreateModalOpen.set(true);
  }

  protected saveNewPocket(): void {
    const name = this.newPocketName().trim();
    const targetMinor = Math.round(this.newPocketTargetRon() * 100);
    if (!name || targetMinor <= 0) {
      this.toast.error('Completează un nume și o sumă țintă validă.');
      return;
    }

    this.creatingPocket.set(true);
    this.banking.createPocket(name, targetMinor).subscribe({
      next: (pocket) => {
        this.pockets.update((list) => [...list, pocket]);
        this.creatingPocket.set(false);
        this.pocketCreateModalOpen.set(false);
        this.toast.success(`Obiectiv "${pocket.name}" creat.`);
      },
      error: (err) => {
        this.creatingPocket.set(false);
        this.toast.error(extractErrorMessage(err, 'Nu am putut crea obiectivul.'));
      },
    });
  }

  protected openDepositModal(pocket: PocketView): void {
    this.depositAmountRon.set(50);
    this.depositModalPocket.set(pocket);
  }

  protected confirmDeposit(): void {
    const pocket = this.depositModalPocket();
    const amountMinor = Math.round(this.depositAmountRon() * 100);
    if (!pocket || amountMinor <= 0) return;

    this.depositBusy.set(true);
    this.banking.depositToPocket(pocket.id, amountMinor).subscribe({
      next: (updated) => {
        this.pockets.update((list) => list.map((p) => (p.id === updated.id ? updated : p)));
        this.depositBusy.set(false);
        this.depositModalPocket.set(null);
        this.toast.success('Sumă alocată obiectivului.');
      },
      error: (err) => {
        this.depositBusy.set(false);
        this.toast.error(extractErrorMessage(err, 'Depunerea a eșuat.'));
      },
    });
  }

  protected withdrawAll(pocket: PocketView): void {
    if (pocket.saved_minor <= 0) return;
    this.banking.withdrawFromPocket(pocket.id, pocket.saved_minor).subscribe({
      next: (updated) => {
        this.pockets.update((list) => list.map((p) => (p.id === updated.id ? updated : p)));
        this.toast.success('Suma a fost eliberată înapoi în contul curent.');
      },
      error: (err) => this.toast.error(extractErrorMessage(err, 'Retragerea a eșuat.')),
    });
  }

  protected deletePocket(pocket: PocketView): void {
    this.banking.deletePocket(pocket.id).subscribe({
      next: () => {
        this.pockets.update((list) => list.filter((p) => p.id !== pocket.id));
        this.toast.success('Obiectiv șters.');
      },
      error: (err) => this.toast.error(extractErrorMessage(err, 'Ștergerea a eșuat.')),
    });
  }

  protected copyIban(account: AccountView): void {
    navigator.clipboard?.writeText(account.iban).then(() => {
      this.copiedId.set(account.id);
      this.toast.success('IBAN copiat în clipboard.');
      setTimeout(() => this.copiedId.set(null), 2000);
    });
  }

  protected goToTransfer(): void {
    this.router.navigate(['/app/transfers']);
  }

  protected goToTransactions(): void {
    this.router.navigate(['/app/transactions']);
  }

  protected openCreateModal(): void {
    this.createModalOpen.set(true);
  }

  protected closeCreateModal(): void {
    if (this.creatingType()) return; // nu închide în timp ce o cerere e în curs
    this.createModalOpen.set(false);
  }

  protected createAccount(event: AccountCreateEvent): void {
    const { type: accountType, documentFilename } = event;
    if (!CREATABLE_ACCOUNT_TYPES.includes(accountType as CreatableAccountType)) return;
    this.creatingType.set(accountType);
    this.banking.createAccount(accountType as CreatableAccountType, documentFilename).subscribe({
      next: (account) => {
        this.accounts.update((list) => [...list, account]);
        this.creatingType.set(null);
        this.createModalOpen.set(false);
        this.toast.success(`${this.catalog[accountType].label} deschis cu succes.`);
      },
      error: (err) => {
        this.creatingType.set(null);
        this.toast.error(extractErrorMessage(err, 'Nu am putut deschide contul.'));
      },
    });
  }

  protected canDelete(account: AccountView): boolean {
    return account.account_type !== 'current';
  }

  protected requestDelete(account: AccountView): void {
    if (!this.canDelete(account)) return;
    if (account.balance_minor > 0) {
      this.toast.error('Golește mai întâi contul — transferă soldul rămas către alt cont al tău, prin Transferuri.');
      return;
    }
    this.pendingDeleteAccount.set(account);
  }

  protected openStatementModal(account: AccountView): void {
    this.statementFrom.set(this.monthStartIso());
    this.statementTo.set(this.todayIso());
    this.statementAccount.set(account);
  }

  protected closeStatementModal(): void {
    if (this.generatingStatement()) return; // nu închide în timp ce PDF-ul se generează
    this.statementAccount.set(null);
  }

  protected downloadStatement(): void {
    const account = this.statementAccount();
    const from = this.statementFrom();
    const to = this.statementTo();
    if (!account || !from || !to) return;
    if (from > to) {
      this.toast.error('Data de start trebuie să fie înaintea datei de final.');
      return;
    }

    this.generatingStatement.set(true);
    this.transactionsApi
      .downloadStatement(new Date(from).toISOString(), new Date(to + 'T23:59:59').toISOString(), account.id)
      .subscribe({
        next: (blob) => {
          this.generatingStatement.set(false);
          const url = URL.createObjectURL(blob);
          const anchor = document.createElement('a');
          anchor.href = url;
          anchor.download = `extras-cont-${account.iban}-${from}_${to}.pdf`;
          anchor.click();
          URL.revokeObjectURL(url);
          this.statementAccount.set(null);
          this.toast.success('Extras de cont generat.');
        },
        error: (err) => {
          this.generatingStatement.set(false);
          this.toast.error(extractErrorMessage(err, 'Nu am putut genera extrasul de cont.'));
        },
      });
  }

  private monthStartIso(): string {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 10);
  }

  private todayIso(): string {
    return new Date().toISOString().slice(0, 10);
  }

  protected confirmDelete(): void {
    const account = this.pendingDeleteAccount();
    if (!account) return;
    this.deleting.set(true);
    this.banking.deleteAccount(account.id).subscribe({
      next: () => {
        this.accounts.update((list) => list.filter((a) => a.id !== account.id));
        this.deleting.set(false);
        this.pendingDeleteAccount.set(null);
        this.toast.success(`${this.catalog[account.account_type].label} șters.`);
      },
      error: (err) => {
        this.deleting.set(false);
        this.pendingDeleteAccount.set(null);
        this.toast.error(extractErrorMessage(err, 'Nu am putut șterge contul.'));
      },
    });
  }
}
