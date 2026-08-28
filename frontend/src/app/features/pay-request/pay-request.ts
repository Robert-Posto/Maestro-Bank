import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';

import { AccountView, BankingService, PaymentRequestView, TransactionView } from '../../services/banking.service';
import { LanguageService } from '../../services/language.service';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { ActionButton } from '../../shared/components/action-button/action-button';
import { Icon } from '../../shared/components/icon/icon';
import { EmptyState } from '../../shared/components/empty-state/empty-state';
import { MoneyPipe } from '../../shared/pipes/money.pipe';
import { TranslatePipe } from '../../shared/pipes/translate.pipe';
import { ToastService } from '../../shared/components/toast/toast.service';
import { extractErrorMessage } from '../../shared/error-utils';

/**
 * Pagina deschisă de link-ul de "Cerere de plată" (vezi Transfers, tab
 * "Solicită plată" — /app/pay/{id}, generat acolo). Vizualizabilă și plătibilă
 * de ORICE user autentificat, nu doar de destinatarul căruia i s-a trimis
 * link-ul — backendul nu ține evidența "cui" a fost trimis (nu e nevoie,
 * vezi app/routers/payment_requests.py).
 *
 * Plata efectivă reutilizează create_transfer în backend (deci și
 * screening-ul de conținut, motorul de fraudă, Guardian) — pagina asta
 * doar afișează rezultatul, nu duplică nicio logică de business.
 */
@Component({
  selector: 'app-pay-request',
  standalone: true,
  imports: [RouterLink, PageHeader, ActionButton, Icon, EmptyState, MoneyPipe, TranslatePipe],
  templateUrl: './pay-request.html',
  styleUrl: './pay-request.css',
})
export class PayRequest implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly banking = inject(BankingService);
  private readonly toast = inject(ToastService);
  private readonly language = inject(LanguageService);

  protected readonly loading = signal(true);
  protected readonly notFound = signal(false);
  protected readonly request = signal<PaymentRequestView | null>(null);
  protected readonly myAccount = signal<AccountView | null>(null);

  protected readonly paying = signal(false);
  protected readonly payError = signal<string | null>(null);
  protected readonly paidTransaction = signal<TransactionView | null>(null);

  protected readonly cancelling = signal(false);

  /** Cererea e a MEA dacă IBAN-ul solicitantului e propriul meu IBAN — nu
   * comparăm user_id-uri (backendul nu-l expune aici), IBAN-ul e suficient
   * și consistent cu restul frontendului (ex. Transfers::goToReview). */
  protected readonly isOwnRequest = computed(() => {
    const req = this.request();
    const account = this.myAccount();
    return !!req && !!account && req.requester_iban === account.iban;
  });

  ngOnInit(): void {
    const requestId = this.route.snapshot.paramMap.get('id');
    if (!requestId) {
      this.loading.set(false);
      this.notFound.set(true);
      return;
    }

    this.banking.getMyAccount().subscribe({ next: (account) => this.myAccount.set(account) });
    this.banking.getPaymentRequest(requestId).subscribe({
      next: (request) => {
        this.request.set(request);
        this.loading.set(false);
      },
      error: () => {
        this.notFound.set(true);
        this.loading.set(false);
      },
    });
  }

  protected pay(): void {
    const req = this.request();
    if (!req) return;

    this.paying.set(true);
    this.payError.set(null);
    this.banking.payPaymentRequest(req.id).subscribe({
      next: (transaction) => {
        this.paying.set(false);
        this.paidTransaction.set(transaction);
        this.toast.success(this.language.t('payRequest.paymentSuccessToast'));
      },
      error: (err) => {
        this.paying.set(false);
        this.payError.set(this.mapPayError(err));
      },
    });
  }

  protected cancelOwnRequest(): void {
    const req = this.request();
    if (!req) return;

    this.cancelling.set(true);
    this.banking.cancelPaymentRequest(req.id).subscribe({
      next: (updated) => {
        this.cancelling.set(false);
        this.request.set(updated);
        this.toast.success(this.language.t('payRequest.requestCancelledToast'));
      },
      error: (err) => {
        this.cancelling.set(false);
        this.toast.error(extractErrorMessage(err, this.language.t('payRequest.cancelError')));
      },
    });
  }

  protected statusLabel(status: PaymentRequestView['status']): string {
    switch (status) {
      case 'open':
        return this.language.t('payRequest.statusOpen');
      case 'paid':
        return this.language.t('payRequest.statusPaid');
      case 'cancelled':
        return this.language.t('payRequest.statusCancelled');
      case 'expired':
        return this.language.t('payRequest.statusExpired');
    }
  }

  private mapPayError(err: unknown): string {
    if (err instanceof HttpErrorResponse) {
      if (err.status === 0) return this.language.t('payRequest.transferServiceUnavailable');
      if (err.status === 409) return this.language.t('payRequest.requestNoLongerActive');
      if (err.status === 400) {
        const detail = err.error?.detail;
        if (typeof detail === 'string') return detail;
      }
    }
    return this.language.t('payRequest.paymentFailedGeneric');
  }
}
