import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { AccountView, BankingService, PocketView } from '../../services/banking.service';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { StatusBadge } from '../../shared/components/status-badge/status-badge';
import { LoadingSkeleton } from '../../shared/components/loading-skeleton/loading-skeleton';
import { EmptyState } from '../../shared/components/empty-state/empty-state';
import { ActionButton } from '../../shared/components/action-button/action-button';
import { Icon } from '../../shared/components/icon/icon';
import { MoneyPipe } from '../../shared/pipes/money.pipe';
import { Modal } from '../../shared/components/modal/modal';
import { ToastService } from '../../shared/components/toast/toast.service';
import { extractErrorMessage } from '../../shared/error-utils';

/**
 * Conturi — vezi task-ul MaestroBank, secțiunea 8. MVP-ul are un singur
 * cont curent RON per user (provizionat automat la register). Pagina e
 * pregătită pentru a afișa mai multe conturi când backendul le va oferi.
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
    Modal,
  ],
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

  // --- Pockets (obiective de economisire) ---------------------------------
  protected readonly pockets = signal<PocketView[]>([]);
  protected readonly pocketsLoading = signal(true);
  protected readonly totalAllocatedMinor = computed(() =>
    this.pockets().reduce((sum, p) => sum + p.saved_minor, 0),
  );

  protected readonly createModalOpen = signal(false);
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

  protected openCreateModal(): void {
    this.newPocketName.set('');
    this.newPocketTargetRon.set(500);
    this.createModalOpen.set(true);
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
        this.createModalOpen.set(false);
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
