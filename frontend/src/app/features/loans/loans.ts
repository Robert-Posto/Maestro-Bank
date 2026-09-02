import { Component, OnDestroy, OnInit, computed, effect, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';

import {
  EmploymentStatus,
  EmploymentTenure,
  LoanApplicationDetails,
  LoanPaymentView,
  LoanPurpose,
  LoanRateView,
  LoanStatus,
  LoanTermMonths,
  LoanView,
  LoansService,
} from '../../services/loans.service';
import { LanguageService } from '../../services/language.service';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { ActionButton } from '../../shared/components/action-button/action-button';
import { LoadingSkeleton } from '../../shared/components/loading-skeleton/loading-skeleton';
import { EmptyState } from '../../shared/components/empty-state/empty-state';
import { Modal } from '../../shared/components/modal/modal';
import { Select, SelectOption } from '../../shared/components/select/select';
import { StatusBadge } from '../../shared/components/status-badge/status-badge';
import { ToggleControl } from '../../shared/components/toggle-control/toggle-control';
import { SwipeCardDeck, SwipeDeckCard } from '../../shared/components/swipe-card-deck/swipe-card-deck';
import { MoneyPipe } from '../../shared/pipes/money.pipe';
import { TranslatePipe } from '../../shared/pipes/translate.pipe';
import { ToastService } from '../../shared/components/toast/toast.service';
import { extractErrorMessage } from '../../shared/error-utils';

const TERM_OPTIONS: LoanTermMonths[] = [12, 24, 36, 60];
const MIN_AMOUNT_RON = 1000;
const MAX_AMOUNT_RON = 50_000;

/** Cartea de explicații — "Cum funcționează" — vezi app-swipe-card-deck.
 * Doar structura + cheile i18n aici; textul tradus e asamblat de
 * `howItWorksCards` (computed) în componentă, ca la copilot.ts. */
type DeckCardKeys = Omit<SwipeDeckCard, 'title' | 'text'> & { titleKey: string; textKey: string };

const HOW_IT_WORKS_CARD_KEYS: DeckCardKeys[] = [
  { kind: 'cover', titleKey: 'loans.howItWorks.coverTitle', textKey: 'loans.howItWorks.coverText' },
  { kind: 'step', step: 1, titleKey: 'loans.howItWorks.step1Title', textKey: 'loans.howItWorks.step1Text' },
  { kind: 'step', step: 2, titleKey: 'loans.howItWorks.step2Title', textKey: 'loans.howItWorks.step2Text' },
  { kind: 'step', step: 3, titleKey: 'loans.howItWorks.step3Title', textKey: 'loans.howItWorks.step3Text' },
  { kind: 'step', step: 4, titleKey: 'loans.howItWorks.step4Title', textKey: 'loans.howItWorks.step4Text' },
  { kind: 'benefit', icon: 'flash', titleKey: 'loans.howItWorks.benefitInstantTitle', textKey: 'loans.howItWorks.benefitInstantText' },
  { kind: 'benefit', icon: 'check', titleKey: 'loans.howItWorks.benefitNoHiddenTitle', textKey: 'loans.howItWorks.benefitNoHiddenText' },
  { kind: 'benefit', icon: 'banknote', titleKey: 'loans.howItWorks.benefitAutoTitle', textKey: 'loans.howItWorks.benefitAutoText' },
  { kind: 'benefit', icon: 'unlock', titleKey: 'loans.howItWorks.benefitPayoffTitle', textKey: 'loans.howItWorks.benefitPayoffText' },
];

/**
 * Credite personale — simulatorul (sumă + termen) e centrul paginii: userul
 * vede rata exactă ÎNAINTE să aplice, fără să ghicească. Formula de
 * amortizare de mai jos (computeInstallmentMinor) e o COPIE exactă a
 * backend-ului (loans-service/app/rates.py::compute_monthly_installment_minor)
 * — sigură de duplicat client-side pentru că e matematică publică, nu o
 * decizie sensibilă. Decizia REALĂ (eligibilitate + execuție) rămâne 100%
 * pe server, la POST /loans/apply — simulatorul e doar o previzualizare
 * instantă.
 */
@Component({
  selector: 'app-loans',
  standalone: true,
  imports: [
    FormsModule,
    DatePipe,
    DecimalPipe,
    PageHeader,
    ActionButton,
    LoadingSkeleton,
    EmptyState,
    Modal,
    Select,
    StatusBadge,
    ToggleControl,
    SwipeCardDeck,
    MoneyPipe,
    TranslatePipe,
  ],
  templateUrl: './loans.html',
  styleUrl: './loans.css',
})
export class Loans implements OnInit, OnDestroy {
  private readonly loansApi = inject(LoansService);
  private readonly toast = inject(ToastService);
  protected readonly language = inject(LanguageService);

  protected readonly termOptions = TERM_OPTIONS;
  protected readonly minAmountRon = MIN_AMOUNT_RON;
  protected readonly maxAmountRon = MAX_AMOUNT_RON;
  /** Cardurile "Cum funcționează", traduse după limba activă (mirror pe
   * copilot.ts::suggestedQuestions). */
  protected readonly howItWorksCards = computed<SwipeDeckCard[]>(() =>
    HOW_IT_WORKS_CARD_KEYS.map((c) => ({
      kind: c.kind,
      icon: c.icon,
      step: c.step,
      title: this.language.t(c.titleKey),
      text: this.language.t(c.textKey),
    })),
  );

  protected readonly rates = signal<LoanRateView[]>([]);
  protected readonly ratesLoading = signal(true);

  protected readonly loans = signal<LoanView[]>([]);
  protected readonly loansLoading = signal(true);

  // --- Simulator ----------------------------------------------------------------
  protected readonly calculatorAmountRon = signal(10_000);
  protected readonly calculatorTerm = signal<LoanTermMonths>(12);
  protected readonly calculatorRate = computed(() => this.rateFor(this.calculatorTerm()) ?? 0);
  protected readonly calculatorInstallmentMinor = computed(() =>
    this.computeInstallmentMinor(Math.round(this.calculatorAmountRon() * 100), this.calculatorRate(), this.calculatorTerm()),
  );
  protected readonly calculatorTotalPaidMinor = computed(() => this.calculatorInstallmentMinor() * this.calculatorTerm());
  protected readonly calculatorTotalInterestMinor = computed(
    () => this.calculatorTotalPaidMinor() - Math.round(this.calculatorAmountRon() * 100),
  );
  /** Numărul afișat efectiv — animat spre `calculatorInstallmentMinor()` la
   * fiecare schimbare, ca rezultatul să "prindă viață" în loc să sară brusc. */
  protected readonly displayedInstallmentMinor = signal(0);

  private animationFrameId: number | null = null;
  private readonly prefersReducedMotion =
    typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // --- Cerere de credit — chestionar, ca la o bancă reală ------------------------
  protected readonly applyModalOpen = signal(false);
  protected readonly applying = signal(false);

  protected readonly applyPurpose = signal<LoanPurpose>('personal_needs');
  protected readonly applyEmploymentStatus = signal<EmploymentStatus>('employed_permanent');
  protected readonly applyIncomeSource = signal('');
  protected readonly applyEmploymentTenure = signal<EmploymentTenure>('1_to_3_years');
  protected readonly applyDeclaredIncomeRon = signal<number | null>(null);
  protected readonly applyHasOtherDebts = signal(false);
  protected readonly applyOtherDebtsRon = signal<number | null>(null);
  protected readonly applyDependentsCount = signal(0);
  protected readonly applyConsent = signal(false);

  protected readonly purposeOptions = computed<SelectOption[]>(() => {
    this.language.language();
    return (
      ['personal_needs', 'home_renovation', 'purchase_goods', 'debt_refinancing', 'education', 'medical', 'vacation', 'other'] as LoanPurpose[]
    ).map((value) => ({ value, label: this.language.t(`loans.purpose.${value}`) }));
  });

  protected readonly employmentStatusOptions = computed<SelectOption[]>(() => {
    this.language.language();
    return (
      ['employed_permanent', 'employed_fixed_term', 'self_employed', 'retired', 'student', 'unemployed'] as EmploymentStatus[]
    ).map((value) => ({ value, label: this.language.t(`loans.employmentStatus.${value}`) }));
  });

  protected readonly employmentTenureOptions = computed<SelectOption[]>(() => {
    this.language.language();
    return (['under_6_months', '6_to_12_months', '1_to_3_years', '3_to_5_years', 'over_5_years'] as EmploymentTenure[]).map(
      (value) => ({ value, label: this.language.t(`loans.employmentTenure.${value}`) }),
    );
  });

  /** Formularul e valid DOAR când toate câmpurile obligatorii sunt completate
   * — verificat înainte de trimitere, ca butonul să reflecte clar de ce nu
   * poate fi apăsat încă (dezactivat, nu doar o eroare după click). */
  protected readonly applyFormValid = computed(() => {
    const incomeValid = (this.applyDeclaredIncomeRon() ?? 0) > 0;
    const otherDebtsValid = !this.applyHasOtherDebts() || (this.applyOtherDebtsRon() ?? -1) >= 0;
    return this.applyIncomeSource().trim().length >= 2 && incomeValid && otherDebtsValid && this.applyConsent();
  });

  protected readonly payoffTarget = signal<LoanView | null>(null);
  protected readonly payingOff = signal(false);

  protected readonly paymentsModalLoan = signal<LoanView | null>(null);
  protected readonly payments = signal<LoanPaymentView[]>([]);
  protected readonly paymentsLoading = signal(false);

  constructor() {
    effect(() => this.animateInstallmentTo(this.calculatorInstallmentMinor()));
  }

  ngOnInit(): void {
    this.loadRates();
    this.loadLoans();
  }

  ngOnDestroy(): void {
    if (this.animationFrameId !== null) cancelAnimationFrame(this.animationFrameId);
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

  /** Formula STANDARD de amortizare (annuity) — vezi doc-comment-ul clasei. */
  private computeInstallmentMinor(amountMinor: number, ratePercentAnnual: number, termMonths: number): number {
    if (!amountMinor || !ratePercentAnnual || !termMonths) return 0;
    const monthlyRate = ratePercentAnnual / 12 / 100;
    if (monthlyRate === 0) return Math.round(amountMinor / termMonths);
    const factor = Math.pow(1 + monthlyRate, termMonths);
    return Math.round((amountMinor * monthlyRate * factor) / (factor - 1));
  }

  private animateInstallmentTo(target: number): void {
    if (this.animationFrameId !== null) cancelAnimationFrame(this.animationFrameId);
    if (this.prefersReducedMotion) {
      this.displayedInstallmentMinor.set(target);
      return;
    }
    const start = this.displayedInstallmentMinor();
    const startTime = performance.now();
    const duration = 280;
    const step = (now: number) => {
      const t = Math.min(1, (now - startTime) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      this.displayedInstallmentMinor.set(Math.round(start + (target - start) * eased));
      if (t < 1) {
        this.animationFrameId = requestAnimationFrame(step);
      } else {
        this.animationFrameId = null;
      }
    };
    this.animationFrameId = requestAnimationFrame(step);
  }

  protected setCalculatorAmount(value: number): void {
    this.calculatorAmountRon.set(Math.min(this.maxAmountRon, Math.max(this.minAmountRon, value || this.minAmountRon)));
  }

  protected scrollToCalculator(): void {
    document.getElementById('calculator')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
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

  /** Textul badge-ului de status e specific creditelor (nu cel generic din
   * app-status-badge, gândit pentru rețineri de tranzacții) — vezi
   * [labelOverride] pe app-status-badge din loans.html. Tonurile implicite
   * (warning/success/error/neutral) rămân corecte, deci nu e nevoie de
   * toneOverride aici. */
  protected loanStatusLabel(status: LoanStatus): string {
    return this.language.t(`loans.status.${status}`);
  }

  // --- Cerere de credit (din simulator) -------------------------------------------

  /** Deschide chestionarul — pornește mereu de la câmpuri goale, ca o
   * cerere anterioară (trimisă sau abandonată) să nu rămână "lipită" pe
   * ecran la o cerere nouă. */
  protected openApplyForm(): void {
    this.applyPurpose.set('personal_needs');
    this.applyEmploymentStatus.set('employed_permanent');
    this.applyIncomeSource.set('');
    this.applyEmploymentTenure.set('1_to_3_years');
    this.applyDeclaredIncomeRon.set(null);
    this.applyHasOtherDebts.set(false);
    this.applyOtherDebtsRon.set(null);
    this.applyDependentsCount.set(0);
    this.applyConsent.set(false);
    this.applyModalOpen.set(true);
  }

  protected closeApplyForm(): void {
    if (this.applying()) return;
    this.applyModalOpen.set(false);
  }

  protected setApplyHasOtherDebts(value: boolean): void {
    this.applyHasOtherDebts.set(value);
    if (!value) this.applyOtherDebtsRon.set(null);
  }

  protected submitApply(): void {
    const amountMinor = Math.round(this.calculatorAmountRon() * 100);
    if (amountMinor <= 0 || !this.applyFormValid()) return;

    const application: LoanApplicationDetails = {
      purpose: this.applyPurpose(),
      employment_status: this.applyEmploymentStatus(),
      income_source: this.applyIncomeSource().trim(),
      employment_tenure: this.applyEmploymentTenure(),
      declared_monthly_income_minor: Math.round((this.applyDeclaredIncomeRon() ?? 0) * 100),
      has_other_debts: this.applyHasOtherDebts(),
      other_debts_monthly_minor: this.applyHasOtherDebts() ? Math.round((this.applyOtherDebtsRon() ?? 0) * 100) : null,
      dependents_count: this.applyDependentsCount(),
      consent_credit_check: this.applyConsent(),
    };

    this.applying.set(true);
    this.loansApi.apply(amountMinor, this.calculatorTerm(), application).subscribe({
      next: () => {
        this.applying.set(false);
        this.applyModalOpen.set(false);
        this.toast.success(this.language.t('loans.applicationSubmittedToast'));
        this.loadLoans();
      },
      error: (err) => {
        this.applying.set(false);
        this.toast.error(extractErrorMessage(err, this.language.t('loans.applySubmitError')));
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
        this.toast.success(this.language.t('loans.payoffDoneToast'));
        this.loadLoans();
      },
      error: (err) => {
        this.payingOff.set(false);
        this.toast.error(extractErrorMessage(err, this.language.t('loans.payoffFailed')));
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
