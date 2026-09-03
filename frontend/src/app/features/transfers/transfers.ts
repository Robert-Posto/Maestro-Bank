import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed, toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { catchError, debounceTime, distinctUntilChanged, of, switchMap } from 'rxjs';
import QRCode from 'qrcode';

import {
  AccountView,
  BankingService,
  Beneficiary,
  PaymentRequestView,
  ScheduleFrequency,
  ScheduledTransferView,
  TopupOperator,
  TransactionView,
} from '../../services/banking.service';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { ActionButton } from '../../shared/components/action-button/action-button';
import { Icon } from '../../shared/components/icon/icon';
import { Modal } from '../../shared/components/modal/modal';
import { ConfirmDialog } from '../../shared/components/confirm-dialog/confirm-dialog';
import { EmptyState } from '../../shared/components/empty-state/empty-state';
import { MoneyPipe } from '../../shared/pipes/money.pipe';
import { DatePipe } from '@angular/common';
import { TRANSACTION_CATEGORIES, categoryLabel } from '../../shared/categories';
import { Select, SelectOption } from '../../shared/components/select/select';
import { ToastService } from '../../shared/components/toast/toast.service';
import { extractErrorMessage } from '../../shared/error-utils';
import { LanguageService } from '../../services/language.service';
import { TranslatePipe } from '../../shared/pipes/translate.pipe';

type TransferStep = 'form' | 'review' | 'success';
type MainTab = 'new' | 'scheduled';
type SendMode = 'send' | 'request' | 'topup';

/**
 * Plăți & Transferuri — vezi task-ul MaestroBank, secțiunea 13.
 * Flow: From account -> Destination IBAN -> Amount -> Description ->
 * Continue -> Review -> Confirm -> Success. Backendul există deja
 * (transactions-service) — doar îl conectăm; după transfer reîmprospătăm
 * sold + tranzacții recente.
 */
@Component({
  selector: 'app-transfers',
  standalone: true,
  imports: [
    FormsModule,
    RouterLink,
    PageHeader,
    ActionButton,
    Icon,
    Modal,
    ConfirmDialog,
    EmptyState,
    MoneyPipe,
    DatePipe,
    Select,
    TranslatePipe,
  ],
  templateUrl: './transfers.html',
  styleUrl: './transfers.css',
})
export class Transfers implements OnInit {
  private readonly banking = inject(BankingService);
  private readonly toast = inject(ToastService);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly language = inject(LanguageService);

  protected readonly categories = TRANSACTION_CATEGORIES;
  protected readonly categoryOptions = computed<SelectOption[]>(() => {
    const lang = this.language.language();
    return TRANSACTION_CATEGORIES.map((c) => ({
      value: c.value,
      label: categoryLabel(c.value, lang),
      colorVar: c.colorVar,
    }));
  });
  protected readonly categoryLabel = categoryLabel;
  protected readonly step = signal<TransferStep>('form');
  protected readonly mainTab = signal<MainTab>('new');
  /** Trimit vs. Solicit — switch în interiorul tabului "Transfer nou", nu
   * mai e un tab separat (vezi discuția cu userul: cardul lung din dreapta
   * n-avea sens, iar un tab la același nivel cu "Programate" pentru o
   * acțiune care e tot despre bani ce circulă pe contul tău era ciudat). */
  protected readonly sendMode = signal<SendMode>('send');

  protected readonly account = signal<AccountView | null>(null);
  protected readonly beneficiaries = signal<Beneficiary[]>([]);
  protected readonly loadingContext = signal(true);

  protected readonly toIban = signal('');
  protected readonly amount = signal<number | null>(null);
  protected readonly description = signal('');
  /** Avertisment LIVE (vezi app/content_screening.py din
   * transactions-service) — actualizat pe măsură ce userul scrie în
   * descriere, ÎNAINTE de a trimite transferul, nu doar după (vezi
   * constructor, mai jos). null = fără avertisment (sau verificare încă
   * în curs / eșuată — fail-open, nu blocăm formularul dacă backend-ul
   * răspunde greu). */
  protected readonly descriptionWarning = signal<string | null>(null);
  protected readonly category = signal('other');
  protected readonly saveBeneficiaryName = signal('');
  protected readonly saveAsBeneficiary = signal(false);

  protected readonly submitting = signal(false);
  protected readonly formError = signal<string | null>(null);
  protected readonly completedTransaction = signal<TransactionView | null>(null);

  protected readonly amountMinor = computed(() => Math.round((this.amount() ?? 0) * 100));

  // --- Transferuri programate/recurente ------------------------------------
  protected readonly scheduledTransfers = signal<ScheduledTransferView[]>([]);
  protected readonly scheduledLoading = signal(true);

  protected readonly scheduleModalOpen = signal(false);
  protected readonly scheduleToIban = signal('');
  protected readonly scheduleAmountRon = signal(100);
  protected readonly scheduleDescription = signal('');
  protected readonly scheduleFrequency = signal<ScheduleFrequency>('monthly');
  protected readonly scheduleSaving = signal(false);

  // --- Cereri de plată (link/QR de tip "Request Money") -------------------
  protected readonly paymentRequests = signal<PaymentRequestView[]>([]);
  protected readonly paymentRequestsLoading = signal(true);

  protected readonly requestAmount = signal<number | null>(null);
  protected readonly requestDescription = signal('');
  protected readonly requestDescriptionWarning = signal<string | null>(null);
  protected readonly requestCreating = signal(false);
  protected readonly requestFormError = signal<string | null>(null);

  /** Cererea deschisă în modalul de distribuire (link + QR) — fie imediat
   * după creare, fie re-deschisă manual dintr-un rând al listei. */
  protected readonly shareRequest = signal<PaymentRequestView | null>(null);
  protected readonly shareQrDataUrl = signal<string | null>(null);
  protected readonly shareQrLoading = signal(false);

  // --- Reîncărcare telefon (diaspora) — al treilea mod, alături de
  // Trimit/Solicit. Debit REAL din cont (vezi banking.service.ts
  // ::createTopup) — doar reîncărcarea efectivă la operator e simulată. ---
  protected readonly topupOperator = signal<TopupOperator>('orange');
  protected readonly topupOperatorOptions: SelectOption[] = [
    { value: 'orange', label: 'Orange' },
    { value: 'vodafone', label: 'Vodafone' },
    { value: 'digi', label: 'Digi' },
    { value: 'telekom', label: 'Telekom' },
  ];
  protected readonly topupPhoneNumber = signal('');
  protected readonly topupAmount = signal<number | null>(null);
  protected readonly topupSubmitting = signal(false);
  protected readonly topupError = signal<string | null>(null);
  protected readonly topupCompletedTransaction = signal<TransactionView | null>(null);
  /** Non-null DOAR când backend-ul a respins cu 428 (nepotrivire de
   * operator detectată de Twilio Lookup) — mesajul vine direct din
   * răspuns, ca userul să vadă exact ce operator real a fost detectat. */
  protected readonly topupMismatchMessage = signal<string | null>(null);

  constructor() {
    // Verificare LIVE a descrierii, direct din câmpul de formular — nu
    // după ce transferul e deja trimis (vezi feedback userului: "vreau sa
    // mi apara in timp real verificarea... fix cand scriu in casuta").
    // debounceTime + distinctUntilChanged: un apel per pauză de scris, nu
    // unul per literă; switchMap anulează automat un apel în curs dacă
    // userul mai scrie între timp (fără condiții de cursă pe răspunsuri
    // vechi care ar sosi întârziat).
    toObservable(this.description)
      .pipe(
        debounceTime(400),
        distinctUntilChanged(),
        switchMap((description) => {
          const trimmed = description.trim();
          if (!trimmed) return of({ warning: null });
          return this.banking.screenTransferDescription(trimmed).pipe(catchError(() => of({ warning: null })));
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(({ warning }) => this.descriptionWarning.set(warning));

    // Aceeași verificare LIVE, dar pentru descrierea cererii de plată (tab
    // "Solicită plată") — flux separat, câmp separat, dar exact același
    // screening determinist reutilizat (banking.screenTransferDescription).
    // Spre deosebire de transferuri, aici avertismentul chiar BLOCHEAZĂ
    // trimiterea formularului (vezi createPaymentRequest, mai jos) — o
    // cerere de plată e un link/QR trimis mai departe, nu o tranzacție
    // privată deja consumată.
    toObservable(this.requestDescription)
      .pipe(
        debounceTime(400),
        distinctUntilChanged(),
        switchMap((description) => {
          const trimmed = description.trim();
          if (!trimmed) return of({ warning: null });
          return this.banking.screenTransferDescription(trimmed).pipe(catchError(() => of({ warning: null })));
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(({ warning }) => this.requestDescriptionWarning.set(warning));
  }

  ngOnInit(): void {
    this.loadingContext.set(true);
    this.banking.getMyAccount().subscribe({
      next: (account) => {
        this.account.set(account);
        this.loadingContext.set(false);
      },
      error: () => this.loadingContext.set(false),
    });
    this.banking.getBeneficiaries().subscribe({ next: (list) => this.beneficiaries.set(list) });
    this.loadScheduledTransfers();
    this.loadPaymentRequests();
  }

  private loadScheduledTransfers(): void {
    this.scheduledLoading.set(true);
    this.banking.getScheduledTransfers().subscribe({
      next: (list) => {
        this.scheduledTransfers.set(list);
        this.scheduledLoading.set(false);
      },
      error: () => this.scheduledLoading.set(false),
    });
  }

  protected openScheduleModal(): void {
    this.scheduleToIban.set('');
    this.scheduleAmountRon.set(100);
    this.scheduleDescription.set('');
    this.scheduleFrequency.set('monthly');
    this.scheduleModalOpen.set(true);
  }

  protected saveSchedule(): void {
    const iban = this.scheduleToIban().trim().toUpperCase().replace(/\s+/g, '');
    const amountMinor = Math.round(this.scheduleAmountRon() * 100);
    if (iban.length < 10 || amountMinor <= 0) {
      this.toast.error(this.language.t('transfers.invalidScheduleFields'));
      return;
    }

    this.scheduleSaving.set(true);
    this.banking
      .createScheduledTransfer({
        to_iban: iban,
        amount_minor: amountMinor,
        description: this.scheduleDescription().trim(),
        frequency: this.scheduleFrequency(),
      })
      .subscribe({
        next: (schedule) => {
          this.scheduledTransfers.update((list) => [...list, schedule]);
          this.scheduleSaving.set(false);
          this.scheduleModalOpen.set(false);
          this.toast.success(this.language.t('transfers.scheduleCreated'));
        },
        error: (err) => {
          this.scheduleSaving.set(false);
          this.toast.error(extractErrorMessage(err, this.language.t('transfers.scheduleCreateError')));
        },
      });
  }

  protected cancelSchedule(schedule: ScheduledTransferView): void {
    this.banking.cancelScheduledTransfer(schedule.id).subscribe({
      next: () => {
        this.scheduledTransfers.update((list) => list.filter((s) => s.id !== schedule.id));
        this.toast.success(this.language.t('transfers.scheduleCancelled'));
      },
      error: (err) => this.toast.error(extractErrorMessage(err, this.language.t('transfers.cancelError'))),
    });
  }

  protected frequencyLabel(frequency: ScheduleFrequency): string {
    return this.language.t(frequency === 'weekly' ? 'common.weekly' : 'common.monthly');
  }

  /** app-select în loc de <select> nativ — vezi budgets.ts::periodOptions,
   * același motiv (popup-ul nativ ignoră tokenii --mb-*, rupe dark mode). */
  protected readonly frequencyOptions = computed<SelectOption[]>(() => {
    this.language.language();
    return [
      { value: 'weekly', label: this.frequencyLabel('weekly') },
      { value: 'monthly', label: this.frequencyLabel('monthly') },
    ];
  });
  protected setScheduleFrequency(value: string): void {
    this.scheduleFrequency.set(value as ScheduleFrequency);
  }

  // --- Cereri de plată (link/QR de tip "Request Money") -------------------

  private loadPaymentRequests(): void {
    this.paymentRequestsLoading.set(true);
    this.banking.getMyPaymentRequests().subscribe({
      next: (list) => {
        this.paymentRequests.set(list);
        this.paymentRequestsLoading.set(false);
      },
      error: () => this.paymentRequestsLoading.set(false),
    });
  }

  protected paymentRequestLink(requestId: string): string {
    return `${window.location.origin}/app/pay/${requestId}`;
  }

  protected paymentRequestStatusLabel(status: PaymentRequestView['status']): string {
    switch (status) {
      case 'open':
        return this.language.t('transfers.requestStatusOpen');
      case 'paid':
        return this.language.t('transfers.requestStatusPaid');
      case 'cancelled':
        return this.language.t('transfers.requestStatusCancelled');
      case 'expired':
        return this.language.t('transfers.requestStatusExpired');
    }
  }

  protected createPaymentRequest(): void {
    this.requestFormError.set(null);
    const amountMinor = Math.round((this.requestAmount() ?? 0) * 100);
    if (amountMinor <= 0) {
      this.requestFormError.set(this.language.t('transfers.invalidAmount'));
      return;
    }
    // Verificarea live (vezi constructor) deja dezactivează butonul, dar
    // un submit prin Enter în formular poate ocoli starea `disabled` a
    // butonului — reverificăm aici. Backendul e sursa reală de adevăr
    // (vezi service.py::create_payment_request, care respinge cu 400),
    // asta e doar UX mai rapid, nu singura protecție.
    if (this.requestDescriptionWarning()) {
      return;
    }

    this.requestCreating.set(true);
    this.banking
      .createPaymentRequest({ amount_minor: amountMinor, description: this.requestDescription().trim() })
      .subscribe({
        next: (request) => {
          this.requestCreating.set(false);
          this.paymentRequests.update((list) => [request, ...list]);
          this.requestAmount.set(null);
          this.requestDescription.set('');
          this.toast.success(this.language.t('transfers.requestCreated'));
          this.openShare(request);
        },
        error: (err) => {
          this.requestCreating.set(false);
          this.requestFormError.set(extractErrorMessage(err, this.language.t('transfers.requestCreateError')));
        },
      });
  }

  /** Deschide modalul cu link + cod QR — fie imediat după creare, fie
   * re-deschis manual dintr-un rând al listei ("Distribuie" pe o cerere
   * încă deschisă). Codul QR e generat client-side (pachetul `qrcode`) —
   * link-ul în sine e tot ce contează, nu ținem un cod QR generat de backend. */
  protected openShare(request: PaymentRequestView): void {
    this.shareRequest.set(request);
    this.shareQrDataUrl.set(null);
    this.shareQrLoading.set(true);
    QRCode.toDataURL(this.paymentRequestLink(request.id), { width: 224, margin: 1 })
      .then((dataUrl) => {
        this.shareQrDataUrl.set(dataUrl);
        this.shareQrLoading.set(false);
      })
      .catch(() => this.shareQrLoading.set(false));
  }

  protected closeShare(): void {
    this.shareRequest.set(null);
    this.shareQrDataUrl.set(null);
  }

  protected copyPaymentLink(requestId: string): void {
    navigator.clipboard?.writeText(this.paymentRequestLink(requestId)).then(() => {
      this.toast.success(this.language.t('transfers.linkCopied'));
    });
  }

  protected cancelPaymentRequest(request: PaymentRequestView): void {
    this.banking.cancelPaymentRequest(request.id).subscribe({
      next: (updated) => {
        this.paymentRequests.update((list) => list.map((r) => (r.id === updated.id ? updated : r)));
        this.toast.success(this.language.t('transfers.requestCancelled'));
        if (this.shareRequest()?.id === updated.id) this.closeShare();
      },
      error: (err) => this.toast.error(extractErrorMessage(err, this.language.t('transfers.cancelError'))),
    });
  }

  protected selectBeneficiary(beneficiary: Beneficiary): void {
    this.toIban.set(beneficiary.iban);
  }

  protected initials(name: string): string {
    const parts = name.trim().split(/\s+/).filter(Boolean);
    if (parts.length === 0) return '?';
    return (parts[0].charAt(0) + (parts[1]?.charAt(0) ?? '')).toUpperCase();
  }

  protected goToReview(): void {
    this.formError.set(null);

    const iban = this.toIban().trim().toUpperCase().replace(/\s+/g, '');
    if (iban.length < 10) {
      this.formError.set(this.language.t('transfers.invalidIban'));
      return;
    }
    if (this.account() && iban === this.account()!.iban) {
      this.formError.set(this.language.t('transfers.cannotTransferToSelf'));
      return;
    }
    if (!this.amount() || this.amount()! <= 0) {
      this.formError.set(this.language.t('transfers.invalidAmount'));
      return;
    }
    if (this.account() && this.amountMinor() > this.account()!.balance_minor) {
      this.formError.set(this.language.t('transfers.insufficientBalanceAmount'));
      return;
    }

    this.toIban.set(iban);
    this.step.set('review');
  }

  protected backToForm(): void {
    this.needsCardPin.set(false);
    this.cardPin.set('');
    this.cardPinRequiredMessage.set('');
    this.step.set('form');
  }

  protected confirmTransfer(): void {
    this.submitting.set(true);
    this.formError.set(null);
    this.sendTransfer(undefined, () => this.submitting.set(false));
  }

  /** "Payment confirmation" (Security settings, Cardul meu) — backend-ul
   * respinge cu 428 dacă transferul depășește pragul și contul sursă
   * cere confirmare (vezi transactions-service/app/service.py). Rămânem
   * pe pasul "review", arătăm caseta de PIN — userul NU reface tot
   * formularul, doar confirmă cu PIN-ul cardului. */
  protected readonly needsCardPin = signal(false);
  protected readonly cardPin = signal('');
  protected readonly cardPinBusy = signal(false);
  protected readonly cardPinRequiredMessage = signal('');

  protected submitCardPinConfirmation(): void {
    if (!/^\d{4}$/.test(this.cardPin())) {
      this.toast.error(this.language.t('transfers.invalidCardPin'));
      return;
    }
    this.cardPinBusy.set(true);
    this.sendTransfer(this.cardPin(), () => this.cardPinBusy.set(false), /* isPinRetry */ true);
  }

  private sendTransfer(cardPin: string | undefined, clearBusy: () => void, isPinRetry = false): void {
    this.banking
      .createTransfer({
        to_iban: this.toIban(),
        amount_minor: this.amountMinor(),
        description: this.description().trim(),
        category: this.category(),
        card_pin: cardPin,
      })
      .subscribe({
        next: (transaction) => {
          clearBusy();
          this.needsCardPin.set(false);
          this.cardPin.set('');
          this.completedTransaction.set(transaction);
          this.step.set('success');
          this.toast.success(this.language.t('transfers.transferSuccess'));
          this.refreshAccount();
          this.maybeSaveBeneficiary();
        },
        error: (err) => {
          clearBusy();
          if (err instanceof HttpErrorResponse && err.status === 428) {
            this.needsCardPin.set(true);
            const detail = err.error?.detail;
            this.cardPinRequiredMessage.set(
              typeof detail === 'string' ? detail : this.language.t('transfers.cardPinRequiredFallback'),
            );
            return;
          }
          if (isPinRetry && err instanceof HttpErrorResponse && err.status === 401) {
            this.toast.error(this.language.t('transfers.wrongPin'));
            this.cardPin.set('');
            return;
          }
          this.needsCardPin.set(false);
          this.formError.set(this.mapTransferError(err));
          this.step.set('form');
        },
      });
  }

  private maybeSaveBeneficiary(): void {
    if (!this.saveAsBeneficiary() || !this.saveBeneficiaryName().trim()) return;
    this.banking.createBeneficiary(this.saveBeneficiaryName().trim(), this.toIban()).subscribe({
      next: (beneficiary) => this.beneficiaries.update((list) => [beneficiary, ...list]),
    });
  }

  private refreshAccount(): void {
    this.banking.getMyAccount().subscribe({ next: (account) => this.account.set(account) });
  }

  private mapTransferError(err: unknown): string {
    if (err instanceof HttpErrorResponse) {
      if (err.status === 0) return this.language.t('transfers.serviceUnavailable');
      if (err.status === 409) return this.language.t('transfers.insufficientBalance409');
      if (err.status === 404) return this.language.t('transfers.destinationNotFound');
      if (err.status === 400) {
        const detail = err.error?.detail;
        if (typeof detail === 'string') return detail;
      }
    }
    return this.language.t('transfers.transferFailedGeneric');
  }

  protected setTopupOperator(value: string): void {
    this.topupOperator.set(value as TopupOperator);
  }

  protected submitTopup(): void {
    this.topupError.set(null);

    const phoneNumber = this.topupPhoneNumber().trim();
    if (!/^07\d{8}$/.test(phoneNumber)) {
      this.topupError.set(this.language.t('transfers.topupInvalidPhone'));
      return;
    }
    const amountMinor = Math.round((this.topupAmount() ?? 0) * 100);
    if (amountMinor <= 0) {
      this.topupError.set(this.language.t('transfers.invalidAmount'));
      return;
    }
    if (this.account() && amountMinor > this.account()!.balance_minor) {
      this.topupError.set(this.language.t('transfers.insufficientBalanceAmount'));
      return;
    }

    this.sendTopup(phoneNumber, amountMinor, /* confirmMismatch */ false);
  }

  /** Userul a confirmat în dialogul de nepotrivire (vezi topupMismatchMessage)
   * — retrimitem EXACT același request, cu confirm_mismatch=true, mirror pe
   * fluxul de confirmare cu PIN de card de la transferuri normale. */
  protected confirmTopupMismatch(): void {
    const phoneNumber = this.topupPhoneNumber().trim();
    const amountMinor = Math.round((this.topupAmount() ?? 0) * 100);
    this.sendTopup(phoneNumber, amountMinor, /* confirmMismatch */ true);
  }

  protected cancelTopupMismatch(): void {
    this.topupMismatchMessage.set(null);
  }

  private sendTopup(phoneNumber: string, amountMinor: number, confirmMismatch: boolean): void {
    this.topupSubmitting.set(true);
    this.banking
      .createTopup({
        operator: this.topupOperator(),
        phone_number: phoneNumber,
        amount_minor: amountMinor,
        confirm_mismatch: confirmMismatch,
      })
      .subscribe({
        next: (transaction) => {
          this.topupSubmitting.set(false);
          this.topupMismatchMessage.set(null);
          this.topupCompletedTransaction.set(transaction);
          this.toast.success(this.language.t('transfers.topupSuccess'));
          this.refreshAccount();
        },
        error: (err) => {
          this.topupSubmitting.set(false);
          if (err instanceof HttpErrorResponse && err.status === 428) {
            const detail = err.error?.detail;
            this.topupMismatchMessage.set(typeof detail === 'string' ? detail : this.language.t('transfers.topupMismatchFallback'));
            return;
          }
          this.topupMismatchMessage.set(null);
          this.topupError.set(this.mapTopupError(err));
        },
      });
  }

  private mapTopupError(err: unknown): string {
    if (err instanceof HttpErrorResponse) {
      if (err.status === 0) return this.language.t('transfers.serviceUnavailable');
      if (err.status === 409) return this.language.t('transfers.insufficientBalance409');
      if (err.status === 502) return this.language.t('transfers.topupOperatorUnavailable');
      if (err.status === 400 || err.status === 422) {
        const detail = err.error?.detail;
        if (typeof detail === 'string') return detail;
      }
    }
    return this.language.t('transfers.topupFailedGeneric');
  }

  protected startNewTopup(): void {
    this.topupPhoneNumber.set('');
    this.topupAmount.set(null);
    this.topupError.set(null);
    this.topupMismatchMessage.set(null);
    this.topupCompletedTransaction.set(null);
  }

  protected startNewTransfer(): void {
    this.toIban.set('');
    this.amount.set(null);
    this.description.set('');
    this.category.set('other');
    this.saveAsBeneficiary.set(false);
    this.saveBeneficiaryName.set('');
    this.completedTransaction.set(null);
    this.needsCardPin.set(false);
    this.cardPin.set('');
    this.cardPinRequiredMessage.set('');
    this.step.set('form');
  }
}
