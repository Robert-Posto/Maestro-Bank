import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { AccountView, BankingService } from '../../services/banking.service';
import {
  HistoryPointView,
  HoldingView,
  InstrumentDetailView,
  InstrumentView,
  InvestmentsService,
} from '../../services/investments.service';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { ActionButton } from '../../shared/components/action-button/action-button';
import { LoadingSkeleton } from '../../shared/components/loading-skeleton/loading-skeleton';
import { EmptyState } from '../../shared/components/empty-state/empty-state';
import { Modal } from '../../shared/components/modal/modal';
import { MoneyPipe } from '../../shared/pipes/money.pipe';
import { ToastService } from '../../shared/components/toast/toast.service';
import { extractErrorMessage } from '../../shared/error-utils';

/**
 * Investiții — cumpărare/vânzare de acțiuni/ETF-uri, catalog curatoriat
 * (16 simboluri), preț REAL (dar dintr-un endpoint NEOFICIAL, vezi
 * InvestmentsService), plus indici bursieri reali (DOAR informativi — nu
 * se cumpără direct). Pagină separată (nu tab pe Conturi) — suprafață
 * prea mare (catalog + indici + portofoliu + tranzacționare + detalii)
 * pentru un tab. Toate instrumentele se tranzacționează în USD — necesită
 * contul USD deschis (vezi accounts-service, aceeași cerință ca Schimb
 * valutar).
 */
@Component({
  selector: 'app-investments',
  standalone: true,
  imports: [FormsModule, DecimalPipe, PageHeader, ActionButton, LoadingSkeleton, EmptyState, Modal, MoneyPipe],
  templateUrl: './investments.html',
  styleUrl: './investments.css',
})
export class Investments implements OnInit {
  private readonly investmentsApi = inject(InvestmentsService);
  private readonly banking = inject(BankingService);
  private readonly toast = inject(ToastService);
  private readonly router = inject(Router);

  protected readonly accounts = signal<AccountView[]>([]);
  protected readonly usdAccount = computed(() => this.accounts().find((a) => a.account_type === 'usd') ?? null);

  protected readonly instruments = signal<InstrumentView[]>([]);
  protected readonly instrumentsLoading = signal(true);

  protected readonly indices = signal<InstrumentView[]>([]);
  protected readonly indicesLoading = signal(true);

  protected readonly portfolio = signal<HoldingView[]>([]);
  protected readonly portfolioLoading = signal(true);
  protected readonly portfolioValueMinor = computed(() =>
    this.portfolio().reduce((sum, h) => sum + h.current_value_minor, 0),
  );
  protected readonly portfolioGainMinor = computed(() =>
    this.portfolio().reduce((sum, h) => sum + h.unrealized_gain_minor, 0),
  );

  /** Catalogul, grupat pe categorii (Tehnologie / Consum & Finanțe / ETF-uri)
   * — ordinea grupurilor urmează ordinea în care apar prima dată în
   * instruments() (backend-ul le trimite deja grupate, vezi app/catalog.py
   * ::CATALOG), nu e hardcodată aici ca să rămână sincronizată automat. */
  protected readonly catalogGroups = computed(() => {
    const groups: { label: string; items: InstrumentView[] }[] = [];
    for (const instrument of this.instruments()) {
      const label = instrument.category ?? 'Altele';
      let group = groups.find((g) => g.label === label);
      if (!group) {
        group = { label, items: [] };
        groups.push(group);
      }
      group.items.push(instrument);
    }
    return groups;
  });

  // --- Detalii, la click (instrument SAU indice) ---------------------------
  protected readonly detailSymbol = signal<string | null>(null);
  protected readonly detailData = signal<InstrumentDetailView | null>(null);
  protected readonly detailLoading = signal(false);
  protected readonly detailError = signal<string | null>(null);

  protected readonly buyModalInstrument = signal<InstrumentView | null>(null);
  protected readonly buyAmountUsd = signal(500);
  protected readonly buying = signal(false);

  protected readonly sellModalHolding = signal<HoldingView | null>(null);
  protected readonly sellQuantity = signal(0);
  protected readonly selling = signal(false);

  ngOnInit(): void {
    this.banking.getAllAccounts().subscribe({ next: (accounts) => this.accounts.set(accounts) });
    this.loadInstruments();
    this.loadIndices();
    this.loadPortfolio();
  }

  private loadInstruments(): void {
    this.instrumentsLoading.set(true);
    this.investmentsApi.listInstruments().subscribe({
      next: (instruments) => {
        this.instruments.set(instruments);
        this.instrumentsLoading.set(false);
      },
      error: () => this.instrumentsLoading.set(false),
    });
  }

  private loadIndices(): void {
    this.indicesLoading.set(true);
    this.investmentsApi.listIndices().subscribe({
      next: (indices) => {
        this.indices.set(indices);
        this.indicesLoading.set(false);
      },
      error: () => this.indicesLoading.set(false),
    });
  }

  private loadPortfolio(): void {
    this.portfolioLoading.set(true);
    this.investmentsApi.getPortfolio().subscribe({
      next: (portfolio) => {
        this.portfolio.set(portfolio);
        this.portfolioLoading.set(false);
      },
      error: () => this.portfolioLoading.set(false),
    });
  }

  private refreshAccountsAndPortfolio(): void {
    this.loadPortfolio();
    this.banking.getAllAccounts().subscribe({ next: (accounts) => this.accounts.set(accounts) });
  }

  protected goToOpenAccount(): void {
    this.router.navigate(['/app/accounts']);
  }

  // --- Detalii (click pe orice card — instrument SAU indice) ---------------

  protected openDetail(symbol: string): void {
    this.detailSymbol.set(symbol);
    this.detailData.set(null);
    this.detailError.set(null);
    this.detailLoading.set(true);
    this.investmentsApi.getDetail(symbol).subscribe({
      next: (detail) => {
        this.detailData.set(detail);
        this.detailLoading.set(false);
      },
      error: (err) => {
        this.detailLoading.set(false);
        this.detailError.set(extractErrorMessage(err, 'Nu am putut încărca detaliile.'));
      },
    });
  }

  protected closeDetail(): void {
    this.detailSymbol.set(null);
    this.detailData.set(null);
  }

  /** Cumpărare direct din panoul de detalii — închide detaliile, deschide
   * modalul de cumpărare, presetat pe același simbol. */
  protected buyFromDetail(): void {
    const detail = this.detailData();
    if (!detail) return;
    const instrument = this.instruments().find((i) => i.symbol === detail.symbol);
    if (!instrument) return;
    this.closeDetail();
    this.openBuyModal(instrument);
  }

  /** Punctele unui sparkline SVG (viewBox 0 0 100 32) — normalizat pe
   * min/max din istoric, ca linia să umple tot spațiul disponibil
   * indiferent de amplitudinea reală a prețului. */
  protected sparklinePoints(history: HistoryPointView[]): string {
    if (history.length < 2) return '';
    const prices = history.map((h) => h.price_minor);
    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const range = max - min || 1;
    return history
      .map((h, i) => {
        const x = (i / (history.length - 1)) * 100;
        const y = 32 - ((h.price_minor - min) / range) * 32;
        return `${x.toFixed(2)},${y.toFixed(2)}`;
      })
      .join(' ');
  }

  protected sparklineTrendPositive(history: HistoryPointView[]): boolean {
    if (history.length < 2) return true;
    return history[history.length - 1].price_minor >= history[0].price_minor;
  }

  /** Poziția (%) pe un "range-bar" (zi sau 52 săptămâni) pentru prețul
   * curent, între low și high. */
  protected rangePositionPercent(low: number, high: number, current: number): number {
    if (high <= low) return 50;
    return Math.min(100, Math.max(0, ((current - low) / (high - low)) * 100));
  }

  // --- Cumpărare -------------------------------------------------------------

  protected openBuyModal(instrument: InstrumentView): void {
    this.buyAmountUsd.set(500);
    this.buyModalInstrument.set(instrument);
  }

  protected closeBuyModal(): void {
    if (this.buying()) return;
    this.buyModalInstrument.set(null);
  }

  protected confirmBuy(): void {
    const instrument = this.buyModalInstrument();
    const amountMinor = Math.round(this.buyAmountUsd() * 100);
    if (!instrument || amountMinor <= 0) return;

    this.buying.set(true);
    this.investmentsApi.buy(instrument.symbol, amountMinor).subscribe({
      next: () => {
        this.buying.set(false);
        this.buyModalInstrument.set(null);
        this.toast.success(`Ai cumpărat ${instrument.symbol} de ${this.buyAmountUsd()} USD.`);
        this.refreshAccountsAndPortfolio();
      },
      error: (err) => {
        this.buying.set(false);
        this.toast.error(extractErrorMessage(err, 'Cumpărarea a eșuat.'));
      },
    });
  }

  // --- Vânzare -----------------------------------------------------------------

  protected openSellModal(holding: HoldingView): void {
    this.sellQuantity.set(holding.quantity);
    this.sellModalHolding.set(holding);
  }

  protected confirmSell(): void {
    const holding = this.sellModalHolding();
    const quantity = this.sellQuantity();
    if (!holding || quantity <= 0 || quantity > holding.quantity) return;

    this.selling.set(true);
    this.investmentsApi.sell(holding.symbol, quantity).subscribe({
      next: () => {
        this.selling.set(false);
        this.sellModalHolding.set(null);
        this.toast.success(`Ai vândut ${quantity} ${holding.symbol}.`);
        this.refreshAccountsAndPortfolio();
      },
      error: (err) => {
        this.selling.set(false);
        this.toast.error(extractErrorMessage(err, 'Vânzarea a eșuat.'));
      },
    });
  }
}
