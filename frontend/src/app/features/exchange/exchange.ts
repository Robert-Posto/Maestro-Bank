import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
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
import { Select, SelectOption } from '../../shared/components/select/select';

/**
 * Schimb valutar — vezi UI reference/Exchange.png și task-ul MaestroBank,
 * secțiunea 15. Cursul de bază (mid_rate) e REAL — preluat zilnic de la
 * BNR de către exchange-service. Spread-ul și comisionul rămân o politică
 * simulată MaestroBank, dar execuția CHIAR mută solduri, între contul RON
 * și contul userului pe valuta țintă — necesită acel cont deschis deja
 * (vezi accounts-service::apply_internal_exchange).
 */
@Component({
  selector: 'app-exchange',
  standalone: true,
  imports: [FormsModule, PageHeader, ActionButton, Icon, MoneyPipe, Select],
  templateUrl: './exchange.html',
  styleUrl: './exchange.css',
})
export class Exchange implements OnInit {
  private readonly exchangeApi = inject(ExchangeService);
  private readonly banking = inject(BankingService);
  private readonly toast = inject(ToastService);
  private readonly router = inject(Router);
  private readonly quoteTrigger = new Subject<void>();

  protected readonly accounts = signal<AccountView[]>([]);
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
  private toSelectOptions(codes: string[]): SelectOption[] {
    return codes.map((code) => ({ value: code, label: code, colorVar: currencyColorVar(code) }));
  }

  protected readonly fromOptions = computed<SelectOption[]>(() =>
    this.toSelectOptions(this.toCurrency() === 'RON' ? this.foreignCurrencies() : ['RON']),
  );
  protected readonly toOptions = computed<SelectOption[]>(() =>
    this.toSelectOptions(this.fromCurrency() === 'RON' ? this.foreignCurrencies() : ['RON']),
  );

  /** Culoarea insignei fiecărei monede (selectoare + lista de cursuri) — vezi shared/currencies.ts. */
  protected currencyColor(code: string): string {
    return currencyColorVar(code);
  }

  /** "RON" -> contul curent; altfel contul pe valuta respectivă (eur/usd/gbp)
   * — exact maparea folosită și de exchange-service (_account_type_for_currency). */
  private accountTypeForCurrency(code: string): string {
    return code === 'RON' ? 'current' : code.toLowerCase();
  }

  protected readonly fromAccount = computed(
    () => this.accounts().find((a) => a.account_type === this.accountTypeForCurrency(this.fromCurrency())) ?? null,
  );
  protected readonly toAccount = computed(
    () => this.accounts().find((a) => a.account_type === this.accountTypeForCurrency(this.toCurrency())) ?? null,
  );
  /** Cursul se poate afișa oricum (nu cere niciun cont) — dar EXECUȚIA
   * chiar mută solduri, deci userul trebuie să aibă deja contul destinație
   * deschis (vezi ExchangeService, doc-comment). */
  protected readonly canExecute = computed(() => !!this.quote() && !!this.toAccount());

  ngOnInit(): void {
    this.loadAccounts();
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

  private loadAccounts(): void {
    this.banking.getAllAccounts().subscribe({ next: (accounts) => this.accounts.set(accounts) });
  }

  protected goToOpenAccount(): void {
    this.router.navigate(['/app/accounts']);
  }

  protected onInputChange(): void {
    this.confirmed.set(false);
    this.quoteTrigger.next();
  }

  protected onFromCurrencyChange(code: string): void {
    this.fromCurrency.set(code);
    this.onInputChange();
  }

  protected onToCurrencyChange(code: string): void {
    this.toCurrency.set(code);
    this.onInputChange();
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
    if (!this.canExecute()) return;
    this.confirming.set(true);
    this.exchangeApi.confirmExchange(this.fromCurrency(), this.toCurrency(), Math.round(this.amount() * 100)).subscribe({
      next: () => {
        this.confirming.set(false);
        this.confirmed.set(true);
        this.toast.success('Schimb valutar realizat — soldurile s-au actualizat.');
        // Soldurile ambelor conturi (sursă + destinație) s-au schimbat efectiv —
        // reîncărcăm ca fx-hint-urile ("Sold disponibil") să reflecte realitatea.
        this.loadAccounts();
      },
      error: (err) => {
        this.confirming.set(false);
        this.toast.error(extractErrorMessage(err, 'Schimbul valutar a eșuat.'));
      },
    });
  }
}
