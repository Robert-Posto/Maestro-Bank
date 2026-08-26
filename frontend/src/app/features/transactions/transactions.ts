import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';
import { ActivatedRoute, Router } from '@angular/router';

import { TransactionView } from '../../services/banking.service';
import { TransactionFilters, TransactionsService } from '../../services/transactions.service';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { StatusBadge } from '../../shared/components/status-badge/status-badge';
import { LoadingSkeleton } from '../../shared/components/loading-skeleton/loading-skeleton';
import { EmptyState } from '../../shared/components/empty-state/empty-state';
import { ActionButton } from '../../shared/components/action-button/action-button';
import { Icon } from '../../shared/components/icon/icon';
import { MoneyPipe } from '../../shared/pipes/money.pipe';
import { TRANSACTION_CATEGORIES, categoryLabel } from '../../shared/categories';
import { transactionDisplayName } from '../../shared/transaction-display';
import { MerchantAvatar } from '../../shared/components/merchant-avatar/merchant-avatar';
import {
  TransactionDetailsPanel,
  TransactionDetail,
} from '../../shared/components/transaction-details-panel/transaction-details-panel';
import { ToastService } from '../../shared/components/toast/toast.service';
import { extractErrorMessage } from '../../shared/error-utils';
import { Select, SelectOption } from '../../shared/components/select/select';

const PAGE_SIZE = 8;

@Component({
  selector: 'app-transactions',
  standalone: true,
  imports: [
    FormsModule,
    DatePipe,
    PageHeader,
    StatusBadge,
    LoadingSkeleton,
    EmptyState,
    ActionButton,
    Icon,
    MoneyPipe,
    MerchantAvatar,
    TransactionDetailsPanel,
    Select,
  ],
  templateUrl: './transactions.html',
  styleUrl: './transactions.css',
})
export class Transactions implements OnInit {
  private readonly transactionsApi = inject(TransactionsService);
  private readonly toast = inject(ToastService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  protected readonly categories = TRANSACTION_CATEGORIES;
  protected readonly categoryLabel = categoryLabel;
  protected readonly displayName = transactionDisplayName;

  /** "Toate categoriile" e opțiunea implicită (value: '') — nu un filtru real. */
  protected readonly categoryOptions: SelectOption[] = [
    { value: '', label: 'Toate categoriile' },
    ...TRANSACTION_CATEGORIES.map((c) => ({ value: c.value, label: c.label, colorVar: c.colorVar })),
  ];

  protected readonly directionOptions: SelectOption[] = [
    { value: '', label: 'Toate' },
    { value: 'incoming', label: 'Încasări' },
    { value: 'outgoing', label: 'Plăți' },
  ];

  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly transactions = signal<TransactionView[]>([]);
  protected readonly page = signal(0);
  protected readonly hasNextPage = signal(false);

  protected readonly filtersOpen = signal(false);

  protected readonly search = signal('');
  protected readonly category = signal('');
  protected readonly direction = signal('');
  protected readonly dateFrom = signal('');
  protected readonly dateTo = signal('');
  protected readonly minAmount = signal<number | null>(null);
  protected readonly maxAmount = signal<number | null>(null);

  protected readonly selectedId = signal<string | null>(null);
  protected readonly recognizing = signal(false);
  protected readonly reporting = signal(false);
  protected readonly exporting = signal(false);
  protected readonly generatingStatement = signal(false);
  protected readonly cancellingHold = signal(false);

  protected readonly selectedTransaction = computed<TransactionDetail | null>(() => {
    const id = this.selectedId();
    return this.transactions().find((t) => t.id === id) ?? null;
  });

  ngOnInit(): void {
    const searchParam = this.route.snapshot.queryParamMap.get('search');
    if (searchParam) {
      this.search.set(searchParam);
    }
    this.load();
  }

  private currentFilters(): TransactionFilters {
    const filters: TransactionFilters = {};
    if (this.search().trim()) filters.search = this.search().trim();
    if (this.category()) filters.category = this.category();
    if (this.direction()) filters.direction = this.direction() as 'incoming' | 'outgoing';
    if (this.dateFrom()) filters.date_from = new Date(this.dateFrom()).toISOString();
    if (this.dateTo()) filters.date_to = new Date(this.dateTo() + 'T23:59:59').toISOString();
    if (this.minAmount() !== null) filters.min_amount_minor = Math.round(this.minAmount()! * 100);
    if (this.maxAmount() !== null) filters.max_amount_minor = Math.round(this.maxAmount()! * 100);
    return filters;
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    const skip = this.page() * PAGE_SIZE;

    // Cerem un rând în plus ca să știm dacă mai există o pagină următoare.
    this.transactionsApi.list(this.currentFilters(), PAGE_SIZE + 1, skip).subscribe({
      next: (items) => {
        this.hasNextPage.set(items.length > PAGE_SIZE);
        this.transactions.set(items.slice(0, PAGE_SIZE));
        this.loading.set(false);
      },
      error: () => {
        this.error.set('Nu am putut încărca tranzacțiile.');
        this.loading.set(false);
      },
    });
  }

  /** Spre deosebire de restul filtrelor (grupate în "Filtre avansate",
   * aplicate DOAR la apăsarea explicită a butonului) — categoria stă în
   * bara principală, ca search-ul, deci se aplică imediat la selecție,
   * nu doar la un pas separat pe care userul ar trebui să-l descopere. */
  protected onCategoryChange(value: string): void {
    this.category.set(value);
    this.applyFilters();
  }

  protected toggleFilters(): void {
    this.filtersOpen.update((open) => !open);
  }

  protected applyFilters(): void {
    this.page.set(0);
    this.router.navigate([], { relativeTo: this.route, queryParams: {} });
    this.load();
  }

  protected resetFilters(): void {
    this.search.set('');
    this.category.set('');
    this.direction.set('');
    this.dateFrom.set('');
    this.dateTo.set('');
    this.minAmount.set(null);
    this.maxAmount.set(null);
    this.applyFilters();
  }

  protected nextPage(): void {
    if (!this.hasNextPage()) return;
    this.page.update((p) => p + 1);
    this.load();
  }

  protected prevPage(): void {
    if (this.page() === 0) return;
    this.page.update((p) => p - 1);
    this.load();
  }

  protected openDetails(id: string): void {
    this.selectedId.set(id);
  }

  protected closeDetails(): void {
    this.selectedId.set(null);
  }

  protected recognize(): void {
    const tx = this.selectedTransaction();
    if (!tx) return;
    this.recognizing.set(true);
    this.transactionsApi.recognize(tx.id).subscribe({
      next: (updated) => {
        this.updateLocal(updated);
        this.recognizing.set(false);
        this.toast.success('Tranzacție marcată ca recunoscută.');
      },
      error: (err) => {
        this.recognizing.set(false);
        this.toast.error(extractErrorMessage(err, 'Nu am putut actualiza tranzacția.'));
      },
    });
  }

  protected report(): void {
    const tx = this.selectedTransaction();
    if (!tx) return;
    this.reporting.set(true);
    this.transactionsApi.report(tx.id, 'Semnalat de utilizator din aplicație').subscribe({
      next: (updated) => {
        this.updateLocal(updated);
        this.reporting.set(false);
        this.toast.success('Tranzacția a fost raportată echipei de suport.');
      },
      error: (err) => {
        this.reporting.set(false);
        this.toast.error(extractErrorMessage(err, 'Nu am putut raporta tranzacția.'));
      },
    });
  }

  protected cancelHold(): void {
    const tx = this.selectedTransaction();
    if (!tx) return;
    this.cancellingHold.set(true);
    this.transactionsApi.cancelHold(tx.id).subscribe({
      next: (updated) => {
        this.updateLocal(updated);
        this.cancellingHold.set(false);
        this.toast.success('Transfer anulat — fondurile au revenit în cont.');
      },
      error: (err) => {
        this.cancellingHold.set(false);
        this.toast.error(extractErrorMessage(err, 'Nu am putut anula transferul.'));
      },
    });
  }

  protected contactSupport(): void {
    const tx = this.selectedTransaction();
    // "transfer" doar dacă e chiar un transfer către alt user MaestroBank
    // (counterparty_name e populat STRICT pentru asta) — altfel categoria
    // reală a tranzacției (shopping, bills etc.) nu are un echivalent 1:1
    // în categoriile de tichet (card/transfer/account/technical/other),
    // deci "account" e cel mai potrivit generic pentru "ceva legat de o
    // tranzacție din contul meu", nu presetăm orbește "transfer" pentru
    // orice tranzacție.
    const category = tx?.counterparty_name ? 'transfer' : 'account';
    this.router.navigate(['/app/support'], { queryParams: { newTicket: '1', category } });
  }

  protected exportCsv(): void {
    this.exporting.set(true);
    this.transactionsApi.exportCsv(this.currentFilters()).subscribe({
      next: (blob) => {
        this.exporting.set(false);
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = 'maestrobank-tranzactii.csv';
        anchor.click();
        URL.revokeObjectURL(url);
        this.toast.success('Export CSV generat.');
      },
      error: (err) => {
        this.exporting.set(false);
        this.toast.error(extractErrorMessage(err, 'Exportul a eșuat.'));
      },
    });
  }

  /** Extras de cont (PDF) — perioada e OBLIGATORIE pe backend, spre deosebire
   * de export CSV; dacă userul n-a completat "Perioadă" din Filtre avansate,
   * cădem pe o valoare implicită rezonabilă (luna curentă), ca butonul să
   * funcționeze imediat, fără să-l forțăm mai întâi să deschidă filtrele. */
  protected downloadStatement(): void {
    const from = this.dateFrom() || this.monthStartIso();
    const to = this.dateTo() || this.todayIso();

    this.generatingStatement.set(true);
    this.transactionsApi
      .downloadStatement(new Date(from).toISOString(), new Date(to + 'T23:59:59').toISOString())
      .subscribe({
        next: (blob) => {
          this.generatingStatement.set(false);
          const url = URL.createObjectURL(blob);
          const anchor = document.createElement('a');
          anchor.href = url;
          anchor.download = `extras-cont-${from}_${to}.pdf`;
          anchor.click();
          URL.revokeObjectURL(url);
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

  private updateLocal(updated: TransactionView): void {
    this.transactions.update((list) => list.map((t) => (t.id === updated.id ? updated : t)));
  }
}
