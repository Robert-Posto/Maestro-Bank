import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';
import { ActivatedRoute } from '@angular/router';

import { SupportService, SupportTicket, TicketCategory } from '../../services/support.service';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { ActionButton } from '../../shared/components/action-button/action-button';
import { StatusBadge } from '../../shared/components/status-badge/status-badge';
import { EmptyState } from '../../shared/components/empty-state/empty-state';
import { LoadingSkeleton } from '../../shared/components/loading-skeleton/loading-skeleton';
import { Modal } from '../../shared/components/modal/modal';
import { Icon } from '../../shared/components/icon/icon';
import { ToastService } from '../../shared/components/toast/toast.service';
import { extractErrorMessage } from '../../shared/error-utils';

const CATEGORY_LABELS: Record<TicketCategory, string> = {
  card: 'Card',
  transfer: 'Transfer',
  account: 'Cont',
  technical: 'Tehnic',
  other: 'Altele',
};

const FAQ_ITEMS = [
  { q: 'Cum blochez temporar cardul?', a: 'Din pagina Carduri, secțiunea Control card, activează "Blocare temporară card".' },
  { q: 'Cum fac un transfer?', a: 'Din Plăți & Transferuri, completează IBAN-ul destinație și suma, apoi confirmă.' },
  { q: 'De ce nu apare o tranzacție?', a: 'Tranzacțiile apar imediat după procesare. Reîmprospătează pagina Tranzacții.' },
  { q: 'Cursul valutar e real?', a: 'Nu — Schimb valutar folosește un motor demo, marcat explicit ca simulare.' },
];

/** Support — vezi task-ul MaestroBank, secțiunea 20. Fără AI. */
@Component({
  selector: 'app-support',
  standalone: true,
  imports: [FormsModule, DatePipe, PageHeader, ActionButton, StatusBadge, EmptyState, LoadingSkeleton, Modal, Icon],
  templateUrl: './support.html',
  styleUrl: './support.css',
})
export class Support implements OnInit {
  private readonly supportApi = inject(SupportService);
  private readonly toast = inject(ToastService);
  private readonly route = inject(ActivatedRoute);

  protected readonly categoryLabels = CATEGORY_LABELS;
  protected readonly faqItems = FAQ_ITEMS;

  protected readonly loading = signal(true);
  protected readonly tickets = signal<SupportTicket[]>([]);
  protected readonly modalOpen = signal(false);
  protected readonly saving = signal(false);

  protected readonly subject = signal('');
  protected readonly category = signal<TicketCategory>('other');
  protected readonly message = signal('');

  ngOnInit(): void {
    this.load();
    const shouldOpen = this.route.snapshot.queryParamMap.get('newTicket') === '1';
    const presetCategory = this.route.snapshot.queryParamMap.get('category') as TicketCategory | null;
    if (presetCategory) this.category.set(presetCategory);
    if (shouldOpen) this.openModal();
  }

  private load(): void {
    this.loading.set(true);
    this.supportApi.listTickets().subscribe({
      next: (tickets) => {
        this.tickets.set(tickets);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  protected openModal(): void {
    this.subject.set('');
    this.message.set('');
    this.modalOpen.set(true);
  }

  protected submitTicket(): void {
    if (!this.subject().trim() || !this.message().trim()) {
      this.toast.error('Completează subiectul și mesajul.');
      return;
    }
    this.saving.set(true);
    this.supportApi
      .createTicket({ subject: this.subject().trim(), category: this.category(), message: this.message().trim() })
      .subscribe({
        next: (ticket) => {
          this.tickets.update((list) => [ticket, ...list]);
          this.saving.set(false);
          this.modalOpen.set(false);
          this.toast.success('Tichet de suport trimis.');
        },
        error: (err) => {
          this.saving.set(false);
          this.toast.error(extractErrorMessage(err, 'Nu am putut trimite tichetul.'));
        },
      });
  }
}
