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
  TransactionView,
} from '../../services/banking.service';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { ActionButton } from '../../shared/components/action-button/action-button';
import { Icon } from '../../shared/components/icon/icon';
import { Modal } from '../../shared/components/modal/modal';
import { EmptyState } from '../../shared/components/empty-state/empty-state';
import { MoneyPipe } from '../../shared/pipes/money.pipe';
import { DatePipe } from '@angular/common';
import { TRANSACTION_CATEGORIES, categoryLabel } from '../../shared/categories';
import { Select, SelectOption } from '../../shared/components/select/select';
import { ToastService } from '../../shared/components/toast/toast.service';
import { extractErrorMessage } from '../../shared/error-utils';

type TransferStep = 'form' | 'review' | 'success';
type MainTab = 'new' | 'scheduled';
type SendMode = 'send' | 'request';

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
  imports: [FormsModule, RouterLink, PageHeader, ActionButton, Icon, Modal, EmptyState, MoneyPipe, DatePipe, Select],
  templateUrl: './transfers.html',
  styleUrl: './transfers.css',
})
export class Transfers implements OnInit {
  private readonly banking = inject(BankingService);
  private readonly toast = inject(ToastService);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly categories = TRANSACTION_CATEGORIES;
  protected readonly categoryOptions: SelectOption[] = TRANSACTION_CATEGORIES.map((c) => ({
    value: c.value,
    label: c.label,
    colorVar: c.colorVar,
  }));
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
      this.toast.error('Completează un IBAN valid și o sumă mai mare decât 0.');
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
          this.toast.success('Transfer programat creat.');
        },
        error: (err) => {
          this.scheduleSaving.set(false);
          this.toast.error(extractErrorMessage(err, 'Nu am putut crea transferul programat.'));
        },
      });
  }

  protected cancelSchedule(schedule: ScheduledTransferView): void {
    this.banking.cancelScheduledTransfer(schedule.id).subscribe({
      next: () => {
        this.scheduledTransfers.update((list) => list.filter((s) => s.id !== schedule.id));
        this.toast.success('Transfer programat anulat.');
      },
      error: (err) => this.toast.error(extractErrorMessage(err, 'Anularea a eșuat.')),
    });
  }

  protected frequencyLabel(frequency: ScheduleFrequency): string {
    return frequency === 'weekly' ? 'Săptămânal' : 'Lunar';
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
        return 'Deschisă';
      case 'paid':
        return 'Plătită';
      case 'cancelled':
        return 'Anulată';
      case 'expired':
        return 'Expirată';
    }
  }

  protected createPaymentRequest(): void {
    this.requestFormError.set(null);
    const amountMinor = Math.round((this.requestAmount() ?? 0) * 100);
    if (amountMinor <= 0) {
      this.requestFormError.set('Introdu o sumă validă, mai mare decât 0.');
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
          this.toast.success('Cerere de plată creată.');
          this.openShare(request);
        },
        error: (err) => {
          this.requestCreating.set(false);
          this.requestFormError.set(extractErrorMessage(err, 'Nu am putut crea cererea de plată.'));
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
      this.toast.success('Link copiat în clipboard.');
    });
  }

  protected cancelPaymentRequest(request: PaymentRequestView): void {
    this.banking.cancelPaymentRequest(request.id).subscribe({
      next: (updated) => {
        this.paymentRequests.update((list) => list.map((r) => (r.id === updated.id ? updated : r)));
        this.toast.success('Cerere de plată anulată.');
        if (this.shareRequest()?.id === updated.id) this.closeShare();
      },
      error: (err) => this.toast.error(extractErrorMessage(err, 'Anularea a eșuat.')),
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
      this.formError.set('IBAN destinație invalid.');
      return;
    }
    if (this.account() && iban === this.account()!.iban) {
      this.formError.set('Nu poți transfera către propriul cont.');
      return;
    }
    if (!this.amount() || this.amount()! <= 0) {
      this.formError.set('Introdu o sumă validă, mai mare decât 0.');
      return;
    }
    if (this.account() && this.amountMinor() > this.account()!.balance_minor) {
      this.formError.set('Sold insuficient pentru această sumă.');
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
      this.toast.error('Introdu PIN-ul cardului (4 cifre).');
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
          this.toast.success('Transfer efectuat cu succes.');
          this.refreshAccount();
          this.maybeSaveBeneficiary();
        },
        error: (err) => {
          clearBusy();
          if (err instanceof HttpErrorResponse && err.status === 428) {
            this.needsCardPin.set(true);
            const detail = err.error?.detail;
            this.cardPinRequiredMessage.set(
              typeof detail === 'string' ? detail : 'Acest transfer necesită confirmare cu PIN-ul cardului.',
            );
            return;
          }
          if (isPinRetry && err instanceof HttpErrorResponse && err.status === 401) {
            this.toast.error('PIN incorect.');
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
      if (err.status === 0) return 'Serviciul de transferuri este indisponibil momentan. Încearcă din nou.';
      if (err.status === 409) return 'Sold insuficient pentru acest transfer.';
      if (err.status === 404) return 'Contul destinație (IBAN) nu există.';
      if (err.status === 400) {
        const detail = err.error?.detail;
        if (typeof detail === 'string') return detail;
      }
    }
    return 'Transferul a eșuat. Verifică datele și încearcă din nou.';
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
