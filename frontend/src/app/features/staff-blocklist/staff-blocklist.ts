import { Component, OnInit, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { BlocklistEntryView, StaffService } from '../../services/staff.service';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { StatusBadge } from '../../shared/components/status-badge/status-badge';
import { LoadingSkeleton } from '../../shared/components/loading-skeleton/loading-skeleton';
import { EmptyState } from '../../shared/components/empty-state/empty-state';
import { ActionButton } from '../../shared/components/action-button/action-button';
import { ConfirmDialog } from '../../shared/components/confirm-dialog/confirm-dialog';
import { Modal } from '../../shared/components/modal/modal';
import { Icon } from '../../shared/components/icon/icon';
import { TranslatePipe } from '../../shared/pipes/translate.pipe';
import { ToastService } from '../../shared/components/toast/toast.service';
import { LanguageService } from '../../services/language.service';
import { extractErrorMessage } from '../../shared/error-utils';

/**
 * Personal — lista de beneficiari blocați (BEN-04, vezi backend
 * app/blocklist.py). Un transfer către un IBAN de aici e refuzat DIRECT,
 * înainte de scoring — nu doar semnalat. Scriere DOAR de personal,
 * niciodată din raportul de fraudă al unui client (vezi docstring-ul
 * modulului backend pentru motiv).
 */
@Component({
  selector: 'app-staff-blocklist',
  standalone: true,
  imports: [DatePipe, FormsModule, PageHeader, StatusBadge, LoadingSkeleton, EmptyState, ActionButton, ConfirmDialog, Modal, Icon, TranslatePipe],
  templateUrl: './staff-blocklist.html',
  styleUrl: './staff-blocklist.css',
})
export class StaffBlocklist implements OnInit {
  private readonly staffApi = inject(StaffService);
  private readonly toast = inject(ToastService);
  protected readonly language = inject(LanguageService);

  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly entries = signal<BlocklistEntryView[]>([]);

  protected readonly addOpen = signal(false);
  protected readonly ibanInput = signal('');
  protected readonly reasonInput = signal('');
  protected readonly saving = signal(false);
  protected readonly addError = signal<string | null>(null);

  protected readonly pendingRemoval = signal<BlocklistEntryView | null>(null);
  protected readonly removing = signal(false);

  ngOnInit(): void {
    this.load();
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.staffApi.listBlocklist().subscribe({
      next: (entries) => {
        this.entries.set(entries);
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set(extractErrorMessage(err, this.language.t('staffBlocklist.loadError')));
        this.loading.set(false);
      },
    });
  }

  protected openAdd(): void {
    this.ibanInput.set('');
    this.reasonInput.set('');
    this.addError.set(null);
    this.addOpen.set(true);
  }

  protected closeAdd(): void {
    if (this.saving()) return;
    this.addOpen.set(false);
  }

  protected submitAdd(): void {
    const iban = this.ibanInput().trim();
    if (!iban) {
      this.addError.set(this.language.t('staffBlocklist.ibanRequired'));
      return;
    }

    this.saving.set(true);
    this.addError.set(null);
    this.staffApi.addToBlocklist(iban, this.reasonInput().trim()).subscribe({
      next: (entry) => {
        this.saving.set(false);
        this.addOpen.set(false);
        this.entries.update((list) => [entry, ...list.filter((e) => e.iban !== entry.iban)]);
        this.toast.success(this.language.t('staffBlocklist.addedToast').replace('{iban}', entry.iban));
      },
      error: (err) => {
        this.saving.set(false);
        this.addError.set(extractErrorMessage(err, this.language.t('staffBlocklist.addError')));
      },
    });
  }

  protected askRemove(entry: BlocklistEntryView): void {
    this.pendingRemoval.set(entry);
  }

  protected cancelRemove(): void {
    if (this.removing()) return;
    this.pendingRemoval.set(null);
  }

  protected confirmRemove(): void {
    const entry = this.pendingRemoval();
    if (!entry) return;

    this.removing.set(true);
    this.staffApi.removeFromBlocklist(entry.id).subscribe({
      next: () => {
        this.removing.set(false);
        this.pendingRemoval.set(null);
        this.entries.update((list) => list.filter((e) => e.id !== entry.id));
        this.toast.success(this.language.t('staffBlocklist.removedToast').replace('{iban}', entry.iban));
      },
      error: (err) => {
        this.removing.set(false);
        this.toast.error(extractErrorMessage(err, this.language.t('staffBlocklist.removeError')));
      },
    });
  }

  protected sourceLabel(entry: BlocklistEntryView): string {
    return this.language.t(entry.source === 'confirmed_fraud_review' ? 'staffBlocklist.sourceAuto' : 'staffBlocklist.sourceManual');
  }
}
