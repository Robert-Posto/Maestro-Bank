import { Component, OnInit, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { LoanPaymentView, LoanRateView, LoanTermMonths, LoanView, LoansService } from '../../services/loans.service';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { ActionButton } from '../../shared/components/action-button/action-button';
import { LoadingSkeleton } from '../../shared/components/loading-skeleton/loading-skeleton';
import { EmptyState } from '../../shared/components/empty-state/empty-state';
import { Modal } from '../../shared/components/modal/modal';
import { StatusBadge } from '../../shared/components/status-badge/status-badge';
import { Select } from '../../shared/components/select/select';
import { MoneyPipe } from '../../shared/pipes/money.pipe';
import { ToastService } from '../../shared/components/toast/toast.service';
import { extractErrorMessage } from '../../shared/error-utils';

const TERM_OPTIONS: LoanTermMonths[] = [12, 24, 36, 60];

/**
 * Credite personale — cerere (sumă + termen), execuție REALĂ prin
 * accounts-service (suma intră imediat în contul curent la aprobare). Rata
 * lunară se calculează cu formula standard de amortizare și se plătește
 * AUTOMAT, lunar, din contul curent — vezi loans-service. Aprobarea
 * verifică REAL eligibilitatea (venitul mediu din istoricul de tranzacții)
 * — o cerere poate fi respinsă, cu motivul exact afișat userului (nu doar
 * un refuz sec). Pagină separată — suprafață comparabilă cu Investițiile
 * (cerere + listă credite + scadențar + istoric plăți + plată anticipată).
 */
@Component({
  selector: 'app-loans',
  standalone: true,
  imports: [FormsModule, DatePipe, PageHeader, ActionButton, LoadingSkeleton, EmptyState, Modal, StatusBadge, Select, MoneyPipe],
  templateUrl: './loans.html',
  styleUrl: './loans.css',
})
export class Loans implements OnInit {
  private readonly loansApi = inject(LoansService);
  private readonly toast = inject(ToastService);

  protected readonly termOptions = TERM_OPTIONS;

  protected readonly rates = signal<LoanRateView[]>([]);
  protected readonly ratesLoading = signal(true);

  protected readonly loans = signal<LoanView[]>([]);
  protected readonly loansLoading = signal(true);

  protected readonly applyModalOpen = signal(false);
  protected readonly newLoanAmountRon = signal(5000);
  protected readonly newLoanTerm = signal<LoanTermMonths>(12);
  protected readonly applying = signal(false);

  protected readonly payoffTarget = signal<LoanView | null>(null);
  protected readonly payingOff = signal(false);

  protected readonly paymentsModalLoan = signal<LoanView | null>(null);
  protected readonly payments = signal<LoanPaymentView[]>([]);
  protected readonly paymentsLoading = signal(false);

  ngOnInit(): void {
    this.loadRates();
    this.loadLoans();
  }

  private loadRates(): void {
    this.ratesLoading.set(true);
    this.loansApi.getRates().subscribe({
      next: (rates) => {
        this.rates.set(rates);
        this.ratesLoading.set(false);
      },
      error: () => this.ratesLoading.set(false),
    });
  }

  private loadLoans(): void {
    this.loansLoading.set(true);
    this.loansApi.listMine().subscribe({
      next: (loans) => {
        this.loans.set(loans);
        this.loansLoading.set(false);
      },
      error: () => this.loansLoading.set(false),
    });
  }

  protected rateFor(term: LoanTermMonths): number | null {
    return this.rates().find((r) => r.term_months === term)?.rate_percent_annual ?? null;
  }

  protected loanProgressPercent(loan: LoanView): number {
    if (loan.term_months <= 0) return 0;
    return Math.min(100, Math.max(0, (loan.payments_made / loan.term_months) * 100));
  }

  protected daysUntilDue(loan: LoanView): number | null {
    if (!loan.next_payment_due_at) return null;
    const ms = new Date(loan.next_payment_due_at).getTime() - Date.now();
    return Math.max(0, Math.ceil(ms / (1000 * 60 * 60 * 24)));
  }

  // --- Cerere de credit ---------------------------------------------------------

  protected openApplyModal(): void {
    this.newLoanAmountRon.set(5000);
    this.newLoanTerm.set(12);
    this.applyModalOpen.set(true);
  }

  protected closeApplyModal(): void {
    if (this.applying()) return;
    this.applyModalOpen.set(false);
  }

  protected submitApply(): void {
    const amountMinor = Math.round(this.newLoanAmountRon() * 100);
    if (amountMinor <= 0) return;

    this.applying.set(true);
    this.loansApi.apply(amountMinor, this.newLoanTerm()).subscribe({
      next: () => {
        this.applying.set(false);
        this.applyModalOpen.set(false);
        this.toast.success('Creditul a fost aprobat — suma e deja în contul tău curent.');
        this.loadLoans();
      },
      error: (err) => {
        this.applying.set(false);
        this.toast.error(extractErrorMessage(err, 'Cererea de credit a fost respinsă.'));
      },
    });
  }

  // --- Plată anticipată -----------------------------------------------------------

  protected requestPayoff(loan: LoanView): void {
    this.payoffTarget.set(loan);
  }

  protected cancelPayoff(): void {
    if (this.payingOff()) return;
    this.payoffTarget.set(null);
  }

  protected confirmPayoff(): void {
    const loan = this.payoffTarget();
    if (!loan) return;

    this.payingOff.set(true);
    this.loansApi.payoff(loan.id).subscribe({
      next: () => {
        this.payingOff.set(false);
        this.payoffTarget.set(null);
        this.toast.success('Credit achitat anticipat.');
        this.loadLoans();
      },
      error: (err) => {
        this.payingOff.set(false);
        this.toast.error(extractErrorMessage(err, 'Plata anticipată a eșuat.'));
      },
    });
  }

  // --- Istoric plăți -----------------------------------------------------------------

  protected openPayments(loan: LoanView): void {
    this.paymentsModalLoan.set(loan);
    this.paymentsLoading.set(true);
    this.payments.set([]);
    this.loansApi.getPayments(loan.id).subscribe({
      next: (payments) => {
        this.payments.set(payments);
        this.paymentsLoading.set(false);
      },
      error: () => this.paymentsLoading.set(false),
    });
  }

  protected closePayments(): void {
    this.paymentsModalLoan.set(null);
  }
}
