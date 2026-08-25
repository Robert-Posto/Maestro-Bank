import { Component, OnInit, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { Router } from '@angular/router';

import { StaffHoldView, StaffService } from '../../services/staff.service';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { StatusBadge, BadgeTone } from '../../shared/components/status-badge/status-badge';
import { LoadingSkeleton } from '../../shared/components/loading-skeleton/loading-skeleton';
import { EmptyState } from '../../shared/components/empty-state/empty-state';
import { ActionButton } from '../../shared/components/action-button/action-button';
import { ConfirmDialog } from '../../shared/components/confirm-dialog/confirm-dialog';
import { Modal } from '../../shared/components/modal/modal';
import { Icon } from '../../shared/components/icon/icon';
import { MoneyPipe } from '../../shared/pipes/money.pipe';
import { ToastService } from '../../shared/components/toast/toast.service';
import { extractErrorMessage } from '../../shared/error-utils';

type PendingAction = { hold: StaffHoldView; kind: 'approve' | 'reject' };

/**
 * Personal — reținerile aflate în așteptare (scor >= prag "hold" — vezi
 * backend app/holds.py). Fiecare rând poartă datele de contact ale
 * clientului (telefon inclus), ca personalul să-l poată suna înainte de a
 * decide. Aprobarea eliberează fondurile către beneficiar; respingerea le
 * întoarce la client — vezi StaffService pentru contractul exact.
 */
@Component({
  selector: 'app-staff-holds',
  standalone: true,
  imports: [DatePipe, PageHeader, StatusBadge, LoadingSkeleton, EmptyState, ActionButton, ConfirmDialog, Modal, Icon, MoneyPipe],
  templateUrl: './staff-holds.html',
  styleUrl: './staff-holds.css',
})
export class StaffHolds implements OnInit {
  private readonly staffApi = inject(StaffService);
  private readonly toast = inject(ToastService);
  private readonly router = inject(Router);

  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly holds = signal<StaffHoldView[]>([]);

  protected readonly pendingAction = signal<PendingAction | null>(null);
  protected readonly resolving = signal(false);

  protected readonly analysisTarget = signal<StaffHoldView | null>(null);

  ngOnInit(): void {
    this.load();
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.staffApi.listHolds().subscribe({
      next: (holds) => {
        this.holds.set(holds);
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set(extractErrorMessage(err, 'Nu am putut încărca reținerile.'));
        this.loading.set(false);
      },
    });
  }

  protected scoreTone(score: number | null): BadgeTone {
    if (score === null) return 'neutral';
    if (score >= 90) return 'error';
    if (score >= 80) return 'warning';
    return 'info';
  }

  protected minutesAgo(createdAt: string): string {
    const minutes = Math.max(0, Math.round((Date.now() - new Date(createdAt).getTime()) / 60_000));
    if (minutes < 60) return `acum ${minutes} min`;
    const hours = Math.round(minutes / 60);
    return `acum ${hours} ${hours === 1 ? 'oră' : 'ore'}`;
  }

  protected viewCustomer(hold: StaffHoldView): void {
    if (!hold.user_id) return;
    this.router.navigate(['/admin/customers', hold.user_id]);
  }

  protected openAnalysis(hold: StaffHoldView): void {
    this.analysisTarget.set(hold);
  }

  protected closeAnalysis(): void {
    this.analysisTarget.set(null);
  }

  protected askApprove(hold: StaffHoldView): void {
    this.pendingAction.set({ hold, kind: 'approve' });
  }

  protected askReject(hold: StaffHoldView): void {
    this.pendingAction.set({ hold, kind: 'reject' });
  }

  protected confirmAction(): void {
    const action = this.pendingAction();
    if (!action) return;

    this.resolving.set(true);
    const request =
      action.kind === 'approve' ? this.staffApi.approveHold(action.hold.id) : this.staffApi.rejectHold(action.hold.id);

    request.subscribe({
      next: () => {
        this.resolving.set(false);
        this.pendingAction.set(null);
        this.holds.update((list) => list.filter((h) => h.id !== action.hold.id));
        this.toast.success(action.kind === 'approve' ? 'Transfer aprobat — fondurile au ajuns la beneficiar.' : 'Transfer respins — fondurile au revenit la client.');
      },
      error: (err) => {
        this.resolving.set(false);
        this.toast.error(extractErrorMessage(err, 'Nu am putut rezolva reținerea.'));
      },
    });
  }

  protected cancelAction(): void {
    if (this.resolving()) return;
    this.pendingAction.set(null);
  }
}
