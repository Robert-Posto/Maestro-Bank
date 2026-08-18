import { CommonModule } from '@angular/common';
import { Component, OnInit, Signal, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { AuthService, AuthUser } from '../../services/auth.service';
import { AccountView, BankingService, CardView, TransactionView } from '../../services/banking.service';

/**
 * Core Banking Test Panel — TEMPORAR, doar pentru verificarea funcțională
 * a fluxului Register -> Login -> Cont RON + IBAN + Card (automat) ->
 * Alimentare demo -> Transfer -> Istoric. Nu este designul final
 * MaestroBank.
 */
@Component({
  selector: 'app-banking-panel',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './banking-panel.html',
  styleUrl: './banking-panel.css',
})
export class BankingPanel implements OnInit {
  protected readonly currentUser: Signal<AuthUser | null>;

  // --- register form ---
  protected readonly registerFirstName = signal('');
  protected readonly registerLastName = signal('');
  protected readonly registerEmail = signal('');
  protected readonly registerPassword = signal('');
  protected readonly registerMessage = signal<string | null>(null);
  protected readonly registerError = signal<string | null>(null);

  // --- login form ---
  protected readonly loginEmail = signal('');
  protected readonly loginPassword = signal('');
  protected readonly loginError = signal<string | null>(null);

  // --- banking data ---
  protected readonly account = signal<AccountView | null>(null);
  protected readonly cards = signal<CardView[]>([]);
  protected readonly transactions = signal<TransactionView[]>([]);
  protected readonly bankingError = signal<string | null>(null);

  // --- demo funding (STRICT development-only) ---
  protected readonly fundAmountRon = signal(100);
  protected readonly isFunding = signal(false);

  // --- transfer ---
  protected readonly transferToIban = signal('');
  protected readonly transferAmountRon = signal(10);
  protected readonly transferDescription = signal('');
  protected readonly isTransferring = signal(false);
  protected readonly transferMessage = signal<string | null>(null);
  protected readonly transferError = signal<string | null>(null);

  constructor(
    private readonly auth: AuthService,
    private readonly banking: BankingService,
  ) {
    this.currentUser = this.auth.currentUser;
  }

  ngOnInit(): void {
    if (this.auth.isAuthenticated()) {
      this.loadCurrentUserAndBanking();
    }
  }

  register(): void {
    this.registerMessage.set(null);
    this.registerError.set(null);

    this.auth
      .register({
        first_name: this.registerFirstName().trim(),
        last_name: this.registerLastName().trim(),
        email: this.registerEmail().trim(),
        password: this.registerPassword(),
      })
      .subscribe({
        next: (user) => {
          this.registerMessage.set(
            `Cont creat: ${user.first_name} ${user.last_name} (${user.email}). Te poți autentifica acum.`,
          );
          this.loginEmail.set(user.email);
          this.registerPassword.set('');
        },
        error: (err) => this.registerError.set(this.extractErrorMessage(err, 'Înregistrarea a eșuat.')),
      });
  }

  login(): void {
    this.loginError.set(null);

    this.auth.login({ email: this.loginEmail().trim(), password: this.loginPassword() }).subscribe({
      next: () => {
        this.loginPassword.set('');
        this.loadCurrentUserAndBanking();
      },
      error: (err) => this.loginError.set(this.extractErrorMessage(err, 'Autentificare eșuată.')),
    });
  }

  logout(): void {
    this.auth.logout();
    this.account.set(null);
    this.cards.set([]);
    this.transactions.set([]);
  }

  refreshBanking(): void {
    this.bankingError.set(null);

    this.banking.getMyAccount().subscribe({
      next: (account) => this.account.set(account),
      error: (err) => this.bankingError.set(this.extractErrorMessage(err, 'Nu am putut încărca contul.')),
    });

    this.banking.getMyCards().subscribe({
      next: (cards) => this.cards.set(cards),
      error: () => this.bankingError.set('Nu am putut încărca cardurile.'),
    });

    this.loadTransactions();
  }

  loadTransactions(): void {
    this.banking.getTransactions().subscribe({
      next: (items) => this.transactions.set(items),
      error: () => this.bankingError.set('Nu am putut încărca tranzacțiile.'),
    });
  }

  addDemoFunds(): void {
    const amountMinor = Math.round(this.fundAmountRon() * 100);
    if (amountMinor <= 0) {
      return;
    }

    this.isFunding.set(true);
    this.banking.devFund(amountMinor).subscribe({
      next: (account) => {
        this.account.set(account);
        this.isFunding.set(false);
      },
      error: (err) => {
        this.isFunding.set(false);
        this.bankingError.set(this.extractErrorMessage(err, 'Alimentarea demo a eșuat.'));
      },
    });
  }

  sendTransfer(): void {
    this.transferMessage.set(null);
    this.transferError.set(null);

    const amountMinor = Math.round(this.transferAmountRon() * 100);
    if (amountMinor <= 0 || !this.transferToIban().trim()) {
      this.transferError.set('Completează IBAN-ul destinație și o sumă validă.');
      return;
    }

    this.isTransferring.set(true);
    this.banking
      .createTransfer({
        to_iban: this.transferToIban().trim(),
        amount_minor: amountMinor,
        description: this.transferDescription().trim(),
      })
      .subscribe({
        next: () => {
          this.isTransferring.set(false);
          this.transferMessage.set('Transfer reușit.');
          this.transferToIban.set('');
          this.transferDescription.set('');
          this.refreshBanking();
        },
        error: (err) => {
          this.isTransferring.set(false);
          this.transferError.set(this.extractErrorMessage(err, 'Transferul a eșuat.'));
        },
      });
  }

  private loadCurrentUserAndBanking(): void {
    this.auth.fetchCurrentUser().subscribe({
      error: () => this.bankingError.set('Nu am putut încărca utilizatorul curent.'),
    });
    this.refreshBanking();
  }

  private extractErrorMessage(err: unknown, fallback: string): string {
    const detail = (err as { error?: { detail?: unknown } })?.error?.detail;

    if (typeof detail === 'string') {
      return detail;
    }

    // Erorile de validare Pydantic (HTTP 422) vin ca listă de obiecte
    // {msg, loc, type, ...}, nu ca string simplu — le extragem și le
    // afișăm, altfel userul vede doar mesajul generic de fallback, fără
    // să știe DE CE a eșuat (ex. parolă prea slabă/scurtă).
    if (Array.isArray(detail) && detail.length > 0) {
      const messages = detail
        .map((issue) => (issue && typeof issue === 'object' ? (issue as { msg?: string }).msg : null))
        .filter((msg): msg is string => typeof msg === 'string' && msg.length > 0)
        .map((msg) => msg.replace(/^Value error,\s*/, ''));

      if (messages.length > 0) {
        return messages.join(' ');
      }
    }

    return fallback;
  }
}
