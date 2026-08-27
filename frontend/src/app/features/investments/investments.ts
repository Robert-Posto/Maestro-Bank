import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { AccountView, BankingService } from '../../services/banking.service';
import { HoldingView, InstrumentView, InvestmentsService } from '../../services/investments.service';
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
 * InvestmentsService). Pagină separată (nu tab pe Conturi) — suprafață
 * prea mare (catalog + portofoliu + tranzacționare) pentru un tab.
 * Toate instrumentele se tranzacționează în USD — necesită contul USD
 * deschis (vezi accounts-service, aceeași cerință ca Schimb valutar).
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

  protected readonly portfolio = signal<HoldingView[]>([]);
  protected readonly portfolioLoading = signal(true);
  protected readonly portfolioValueMinor = computed(() =>
    this.portfolio().reduce((sum, h) => sum + h.current_value_minor, 0),
  );
  protected readonly portfolioGainMinor = computed(() =>
    this.portfolio().reduce((sum, h) => sum + h.unrealized_gain_minor, 0),
  );

  protected readonly buyModalInstrument = signal<InstrumentView | null>(null);
  protected readonly buyAmountUsd = signal(500);
  protected readonly buying = signal(false);

  protected readonly sellModalHolding = signal<HoldingView | null>(null);
  protected readonly sellQuantity = signal(0);
  protected readonly selling = signal(false);

  ngOnInit(): void {
    this.banking.getAllAccounts().subscribe({ next: (accounts) => this.accounts.set(accounts) });
    this.loadInstruments();
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

  protected goToOpenAccount(): void {
    this.router.navigate(['/app/accounts']);
  }

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
        this.loadPortfolio();
        this.banking.getAllAccounts().subscribe({ next: (accounts) => this.accounts.set(accounts) });
      },
      error: (err) => {
        this.buying.set(false);
        this.toast.error(extractErrorMessage(err, 'Cumpărarea a eșuat.'));
      },
    });
  }

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
        this.loadPortfolio();
        this.banking.getAllAccounts().subscribe({ next: (accounts) => this.accounts.set(accounts) });
      },
      error: (err) => {
        this.selling.set(false);
        this.toast.error(extractErrorMessage(err, 'Vânzarea a eșuat.'));
      },
    });
  }
}
