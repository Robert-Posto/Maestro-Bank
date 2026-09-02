import { Component, OnInit, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { LoanApplicationStaffView, StaffService } from '../../services/staff.service';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { StatusBadge, BadgeTone } from '../../shared/components/status-badge/status-badge';
import { LoadingSkeleton } from '../../shared/components/loading-skeleton/loading-skeleton';
import { EmptyState } from '../../shared/components/empty-state/empty-state';
import { ActionButton } from '../../shared/components/action-button/action-button';
import { Modal } from '../../shared/components/modal/modal';
import { Icon } from '../../shared/components/icon/icon';
import { MoneyPipe } from '../../shared/pipes/money.pipe';
import { TranslatePipe } from '../../shared/pipes/translate.pipe';
import { ToastService } from '../../shared/components/toast/toast.service';
import { LanguageService } from '../../services/language.service';
import { extractErrorMessage } from '../../shared/error-utils';

/**
 * Personal — cererile de credit în așteptare (status "pending_review", vezi
 * backend loans-service/app/service.py::list_pending_applications, ordonate
 * FIFO). Aprobarea acordă banii REAL pe contul curent al clientului;
 * respingerea nu mută niciun ban, doar înregistrează un motiv — vezi
 * StaffService pentru contractul exact. `eligibility` e un SEMNAL automat
 * (venit real din istoric, nu declarat) — ofițerul de credit decide, nu
 * sistemul; `recommended: false` NU respinge automat cererea.
 */
@Component({
  selector: 'app-staff-loan-applications',
  standalone: true,
  imports: [DatePipe, FormsModule, PageHeader, StatusBadge, LoadingSkeleton, EmptyState, ActionButton, Modal, Icon, MoneyPipe, TranslatePipe],
  templateUrl: './staff-loan-applications.html',
  styleUrl: './staff-loan-applications.css',
})
export class StaffLoanApplications implements OnInit {
  private readonly staffApi = inject(StaffService);
  private readonly toast = inject(ToastService);
  protected readonly language = inject(LanguageService);

  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly applications = signal<LoanApplicationStaffView[]>([]);

  protected readonly detailsTarget = signal<LoanApplicationStaffView | null>(null);

  protected readonly approvingId = signal<string | null>(null);

  protected readonly rejectTarget = signal<LoanApplicationStaffView | null>(null);
  protected readonly rejectReason = signal('');
  protected readonly rejecting = signal(false);
  protected readonly rejectError = signal<string | null>(null);

  ngOnInit(): void {
    this.load();
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.staffApi.listLoanApplications().subscribe({
      next: (applications) => {
        this.applications.set(applications);
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set(extractErrorMessage(err, this.language.t('staffLoanApplications.loadError')));
        this.loading.set(false);
      },
    });
  }

  protected applicantName(app: LoanApplicationStaffView): string {
    if (!app.applicant) return this.language.t('staffLoanApplications.unknownApplicant');
    return `${app.applicant.first_name} ${app.applicant.last_name}`.trim();
  }

  protected purposeLabel(app: LoanApplicationStaffView): string {
    return this.language.t(`loans.purpose.${app.application.purpose}`);
  }

  protected employmentStatusLabel(app: LoanApplicationStaffView): string {
    return this.language.t(`loans.employmentStatus.${app.application.employment_status}`);
  }

  protected employmentTenureLabel(app: LoanApplicationStaffView): string {
    return this.language.t(`loans.employmentTenure.${app.application.employment_tenure}`);
  }

  protected eligibilityTone(app: LoanApplicationStaffView): BadgeTone {
    return app.eligibility.recommended ? 'success' : 'warning';
  }

  protected eligibilityLabel(app: LoanApplicationStaffView): string {
    return this.language.t(
      app.eligibility.recommended ? 'staffLoanApplications.recommended' : 'staffLoanApplications.notRecommended',
    );
  }

  protected openDetails(app: LoanApplicationStaffView): void {
    this.detailsTarget.set(app);
  }

  protected closeDetails(): void {
    this.detailsTarget.set(null);
  }

  protected approve(app: LoanApplicationStaffView): void {
    this.approvingId.set(app.id);
    this.staffApi.approveLoanApplication(app.id).subscribe({
      next: () => {
        this.approvingId.set(null);
        this.detailsTarget.set(null);
        this.applications.update((list) => list.filter((a) => a.id !== app.id));
        this.toast.success(this.language.t('staffLoanApplications.approveToast'));
      },
      error: (err) => {
        this.approvingId.set(null);
        this.toast.error(extractErrorMessage(err, this.language.t('staffLoanApplications.approveError')));
      },
    });
  }

  protected askReject(app: LoanApplicationStaffView): void {
    this.rejectTarget.set(app);
    this.rejectReason.set('');
    this.rejectError.set(null);
  }

  protected cancelReject(): void {
    if (this.rejecting()) return;
    this.rejectTarget.set(null);
  }

  protected confirmReject(): void {
    const app = this.rejectTarget();
    if (!app) return;
    const reason = this.rejectReason().trim();
    if (reason.length < 3) {
      this.rejectError.set(this.language.t('staffLoanApplications.reasonRequired'));
      return;
    }

    this.rejecting.set(true);
    this.rejectError.set(null);
    this.staffApi.rejectLoanApplication(app.id, reason).subscribe({
      next: () => {
        this.rejecting.set(false);
        this.rejectTarget.set(null);
        this.detailsTarget.set(null);
        this.applications.update((list) => list.filter((a) => a.id !== app.id));
        this.toast.success(this.language.t('staffLoanApplications.rejectToast'));
      },
      error: (err) => {
        this.rejecting.set(false);
        this.rejectError.set(extractErrorMessage(err, this.language.t('staffLoanApplications.rejectError')));
      },
    });
  }
}
