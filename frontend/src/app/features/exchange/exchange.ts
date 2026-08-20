import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { debounceTime, distinctUntilChanged, Subject } from 'rxjs';

import { AccountView, BankingService } from '../../services/banking.service';
import { ExchangeQuote, ExchangeRate, ExchangeService } from '../../services/exchange.service';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { ActionButton } from '../../shared/components/action-button/action-button';
import { Icon } from '../../shared/components/icon/icon';
import { MoneyPipe } from '../../shared/pipes/money.pipe';
import { ToastService } from '../../shared/components/toast/toast.service';
import { extractErrorMessage } from '../../shared/error-utils';
import { currencyColorVar } from '../../shared/currencies';

/**
 * Schimb valutar — vezi UI reference/Exchange.png și task-ul MaestroBank,
 * secțiunea 15. Cursul de bază (mid_rate) e REAL — preluat zilnic de la
 * BNR de către exchange-service. ⚠️ Spread-ul, comisionul și execuția
 * (confirmarea schimbului) rămân o simulare MaestroBank — fără mutare
 * reală de fonduri, "is_demo: true" pe fiecare răspuns.
 */
@Component({
  selector: 'app-exchange',
  standalone: true,
  imports: [FormsModule, PageHeader, ActionButton, Icon, MoneyPipe],
  templateUrl: './exchange.html',
  styleUrl: './exchange.css',
})
export class Exchange implements OnInit {
  private readonly exchangeApi = inject(ExchangeService);
  private readonly banking = inject(BankingService);
  private readonly toast = inject(ToastService);
  private readonly quoteTrigger = new Subject<void>();

  protected readonly account = signal<AccountView | null>(null);
  protected readonly rates = signal<ExchangeRate[]>([]);
  protected readonly loadingRates = signal(true);

  protected readonly fromCurrency = signal('RON');
  protected readonly toCurrency = signal('EUR');
  protected readonly amount = signal(5000);

  protected readonly quote = signal<ExchangeQuote | null>(null);
  protected readonly quoting = signal(false);
  protected readonly quoteError = signal<string | null>(null);

  protected readonly confirming = signal(false);
  protected readonly confirmed = signal(false);

  protected readonly foreignCurrencies = computed(() => this.rates().map((r) => r.currency));

  /**
   * Backend-ul suportă STRICT perechi RON <-> valută străină, nu perechi
   * între două valute străine (vezi exchange-service/app/service.py::_foreign_currency,
   * care respinge cu 400 orice pereche fără RON). Constrângem fiecare
   * dropdown la opțiunile valide dat fiind celălalt selector, ca userul să
   * nu poată alege manual o pereche imposibilă (ex. EUR -> USD) — partea
   * de RON se schimbă doar prin butonul de inversare (swap).
   */
  protected readonly fromOptions = computed(() =>
    this.toCurrency() === 'RON' ? this.foreignCurrencies() : ['RON'],
  );
  protected readonly toOptions = computed(() =>
    this.fromCurrency() === 'RON' ? this.foreignCurrencies() : ['RON'],
  );

  /** Culoarea insignei fiecărei monede (selectoare + lista de cursuri) — vezi shared/currencies.ts. */
  protected currencyColor(code: string): string {
    return currencyColorVar(code);
  }

  ngOnInit(): void {
    this.banking.getMyAccount().subscribe({ next: (account) => this.account.set(account) });
    this.exchangeApi.getRates().subscribe({
      next: (rates) => {
        this.rates.set(rates);
        this.loadingRates.set(false);
        this.refreshQuote();
      },
      error: () => this.loadingRates.set(false),
    });

    this.quoteTrigger.pipe(debounceTime(350), distinctUntilChanged()).subscribe(() => this.fetchQuote());
  }

  protected onInputChange(): void {
    this.confirmed.set(false);
    this.quoteTrigger.next();
  }

  protected swapCurrencies(): void {
    const from = this.fromCurrency();
    this.fromCurrency.set(this.toCurrency());
    this.toCurrency.set(from);
    this.onInputChange();
  }

  private refreshQuote(): void {
    this.fetchQuote();
  }

  private fetchQuote(): void {
    if (!this.amount() || this.amount() <= 0) {
      this.quote.set(null);
      return;
    }
    if (this.fromCurrency() === this.toCurrency()) {
      this.quoteError.set('Alege două monede diferite.');
      this.quote.set(null);
      return;
    }

    this.quoting.set(true);
    this.quoteError.set(null);
    const amountMinor = Math.round(this.amount() * 100);

    this.exchangeApi.getQuote(this.fromCurrency(), this.toCurrency(), amountMinor).subscribe({
      next: (quote) => {
        this.quote.set(quote);
        this.quoting.set(false);
      },
      error: (err) => {
        this.quote.set(null);
        this.quoting.set(false);
        this.quoteError.set(extractErrorMessage(err, 'Nu am putut calcula cursul pentru această pereche.'));
      },
    });
  }

  protected confirmExchange(): void {
    if (!this.quote()) return;
    this.confirming.set(true);
    this.exchangeApi.confirmDemoExchange(this.fromCurrency(), this.toCurrency(), Math.round(this.amount() * 100)).subscribe({
      next: () => {
        this.confirming.set(false);
        this.confirmed.set(true);
        this.toast.success('Simulare de schimb valutar înregistrată (demo — fără mutare reală de fonduri).');
      },
      error: (err) => {
        this.confirming.set(false);
        this.toast.error(extractErrorMessage(err, 'Simularea a eșuat.'));
      },
    });
  }
}
