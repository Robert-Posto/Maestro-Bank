import { Component, OnInit, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { StaffCustomerSearchResult, StaffDocumentView, StaffService } from '../../services/staff.service';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { StatusBadge, BadgeTone } from '../../shared/components/status-badge/status-badge';
import { LoadingSkeleton } from '../../shared/components/loading-skeleton/loading-skeleton';
import { EmptyState } from '../../shared/components/empty-state/empty-state';
import { ActionButton } from '../../shared/components/action-button/action-button';
import { ConfirmDialog } from '../../shared/components/confirm-dialog/confirm-dialog';
import { Modal } from '../../shared/components/modal/modal';
import { Icon } from '../../shared/components/icon/icon';
import { ToastService } from '../../shared/components/toast/toast.service';
import { extractErrorMessage } from '../../shared/error-utils';

const MAX_PDF_BYTES = 5 * 1024 * 1024; // 5MB — vezi backend DocumentCreate.pdf_data (max_length=7_000_000 encodat)
let searchDebounceTimer: ReturnType<typeof setTimeout> | undefined;

/**
 * Personal — trimitere de documente (PDF) unui client, pentru semnare
 * virtuală (eSign) — vezi support-service/app/routers/staff.py. Client
 * ales prin căutare (nume/email), fără user_id cunoscut în avans.
 */
@Component({
  selector: 'app-staff-documents',
  standalone: true,
  imports: [DatePipe, FormsModule, PageHeader, StatusBadge, LoadingSkeleton, EmptyState, ActionButton, ConfirmDialog, Modal, Icon],
  templateUrl: './staff-documents.html',
  styleUrl: './staff-documents.css',
})
export class StaffDocuments implements OnInit {
  private readonly staffApi = inject(StaffService);
  private readonly toast = inject(ToastService);

  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly documents = signal<StaffDocumentView[]>([]);

  protected readonly sendOpen = signal(false);
  protected readonly customerQuery = signal('');
  protected readonly customerResults = signal<StaffCustomerSearchResult[]>([]);
  protected readonly customerSearching = signal(false);
  protected readonly selectedCustomer = signal<StaffCustomerSearchResult | null>(null);
  protected readonly titleInput = signal('');
  protected readonly fileName = signal('');
  private pdfDataUri: string | null = null;
  protected readonly saving = signal(false);
  protected readonly sendError = signal<string | null>(null);

  protected readonly pendingCancel = signal<StaffDocumentView | null>(null);
  protected readonly cancelling = signal(false);

  ngOnInit(): void {
    this.load();
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.staffApi.listSentDocuments().subscribe({
      next: (documents) => {
        this.documents.set(documents);
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set(extractErrorMessage(err, 'Nu am putut încărca documentele trimise.'));
        this.loading.set(false);
      },
    });
  }

  protected statusTone(status: StaffDocumentView['status']): BadgeTone {
    if (status === 'signed') return 'success';
    if (status === 'cancelled') return 'neutral';
    return 'warning';
  }

  protected statusLabel(status: StaffDocumentView['status']): string {
    if (status === 'signed') return 'Semnat';
    if (status === 'cancelled') return 'Anulat';
    return 'În așteptare';
  }

  // --- Trimitere document nou -----------------------------------------------

  protected openSend(): void {
    this.customerQuery.set('');
    this.customerResults.set([]);
    this.selectedCustomer.set(null);
    this.titleInput.set('');
    this.fileName.set('');
    this.pdfDataUri = null;
    this.sendError.set(null);
    this.sendOpen.set(true);
  }

  protected closeSend(): void {
    if (this.saving()) return;
    this.sendOpen.set(false);
  }

  protected onCustomerQueryChange(value: string): void {
    this.customerQuery.set(value);
    this.selectedCustomer.set(null);
    clearTimeout(searchDebounceTimer);

    const trimmed = value.trim();
    if (!trimmed) {
      this.customerResults.set([]);
      return;
    }

    searchDebounceTimer = setTimeout(() => {
      this.customerSearching.set(true);
      this.staffApi.searchCustomers(trimmed).subscribe({
        next: (results) => {
          this.customerResults.set(results);
          this.customerSearching.set(false);
        },
        error: () => this.customerSearching.set(false),
      });
    }, 300);
  }

  protected selectCustomer(customer: StaffCustomerSearchResult): void {
    this.selectedCustomer.set(customer);
    this.customerResults.set([]);
    this.customerQuery.set(`${customer.first_name} ${customer.last_name} (${customer.email})`);
  }

  protected onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] ?? null;
    input.value = ''; // reset — re-selectarea ACELUIAȘI fișier trebuie să declanșeze din nou (change)
    if (!file) return;

    if (file.type !== 'application/pdf') {
      this.sendError.set('Alege un fișier PDF.');
      return;
    }
    if (file.size > MAX_PDF_BYTES) {
      this.sendError.set('Fișierul este prea mare (limită 5MB).');
      return;
    }

    this.sendError.set(null);
    const reader = new FileReader();
    reader.onerror = () => this.sendError.set('Nu am putut citi fișierul — încearcă din nou.');
    reader.onload = () => {
      this.pdfDataUri = reader.result as string;
      this.fileName.set(file.name);
    };
    reader.readAsDataURL(file);
  }

  protected submitSend(): void {
    const customer = this.selectedCustomer();
    const title = this.titleInput().trim();

    if (!customer) {
      this.sendError.set('Alege un client din rezultatele căutării.');
      return;
    }
    if (!title) {
      this.sendError.set('Titlul este obligatoriu.');
      return;
    }
    if (!this.pdfDataUri) {
      this.sendError.set('Alege un fișier PDF.');
      return;
    }

    this.saving.set(true);
    this.sendError.set(null);
    this.staffApi.sendDocument(customer.id, title, this.pdfDataUri).subscribe({
      next: (doc) => {
        this.saving.set(false);
        this.sendOpen.set(false);
        this.documents.update((list) => [doc, ...list]);
        this.toast.success(`Documentul a fost trimis către ${customer.first_name} ${customer.last_name}.`);
      },
      error: (err) => {
        this.saving.set(false);
        this.sendError.set(extractErrorMessage(err, 'Nu am putut trimite documentul.'));
      },
    });
  }

  // --- Anulare ---------------------------------------------------------------

  protected askCancel(doc: StaffDocumentView): void {
    this.pendingCancel.set(doc);
  }

  protected cancelDialogClose(): void {
    if (this.cancelling()) return;
    this.pendingCancel.set(null);
  }

  protected confirmCancel(): void {
    const target = this.pendingCancel();
    if (!target) return;

    this.cancelling.set(true);
    this.staffApi.cancelDocument(target.id).subscribe({
      next: () => {
        this.cancelling.set(false);
        this.pendingCancel.set(null);
        this.documents.update((list) => list.map((d) => (d.id === target.id ? { ...d, status: 'cancelled' } : d)));
        this.toast.success('Documentul a fost anulat.');
      },
      error: (err) => {
        this.cancelling.set(false);
        this.toast.error(extractErrorMessage(err, 'Nu am putut anula documentul.'));
      },
    });
  }
}
