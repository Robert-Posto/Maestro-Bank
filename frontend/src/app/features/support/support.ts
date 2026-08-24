import { Component, ElementRef, OnInit, effect, inject, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';
import { ActivatedRoute } from '@angular/router';

import { AiChatMessage as AiHistoryMessage, AiPendingAction, AiSupportService } from '../../services/ai-support.service';
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
import { TransactionRow, TransactionRowData } from '../../shared/components/transaction-row/transaction-row';
import { MoneyPipe } from '../../shared/pipes/money.pipe';

/** Statusul unui card, exact cum îl întoarce accounts-service (CardOut) — vezi
 * app/tools/support_cards_tools.py::get_card_status din ai-orchestrator-service. */
interface ChatCardContext {
  last_four: string;
  status: string;
  is_frozen: boolean;
  online_payments_enabled: boolean;
  contactless_enabled: boolean;
  atm_withdrawals_enabled: boolean;
  international_payments_enabled: boolean;
  daily_limit_minor: number;
}

interface ChatAccountContext {
  iban: string;
  currency: string;
  balance_minor: number;
  status: string;
}

/** Date structurate atașate unui răspuns al Support Agent — populate
 * determinist de backend, din rezultatul BRUT al tool-urilor apelate (NU
 * parafrazate de LLM), ca să poată fi randate cu UI real, nu doar text. */
interface ChatContext {
  transactions?: TransactionRowData[];
  transaction?: TransactionRowData;
  card?: ChatCardContext;
  cards?: ChatCardContext[];
  account?: ChatAccountContext;
  tickets?: SupportTicket[];
}

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

interface ChatMessage {
  id: number;
  role: 'support' | 'user';
  text: string;
  time: string;
  context?: ChatContext;
}

function formatChatTime(date: Date): string {
  return date.toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' });
}

/** Suport minimal de formatare pentru răspunsurile Support Agent — DOAR
 * `**bold**` -> <strong> și linii noi păstrate (vezi .support-chat__bubble
 * { white-space: pre-line } în CSS). Escapăm HTML-ul ÎNAINTE de a insera
 * tag-uri proprii, ca textul modelului să nu poată injecta markup. */
function formatChatText(text: string): string {
  const escaped = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  return escaped.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
}

/** Support — vezi task-ul MaestroBank, secțiunea 20. Fără AI. */
@Component({
  selector: 'app-support',
  standalone: true,
  imports: [
    FormsModule,
    DatePipe,
    MoneyPipe,
    PageHeader,
    ActionButton,
    StatusBadge,
    EmptyState,
    LoadingSkeleton,
    Modal,
    Icon,
    TransactionRow,
  ],
  templateUrl: './support.html',
  styleUrl: './support.css',
})
export class Support implements OnInit {
  private readonly supportApi = inject(SupportService);
  private readonly aiSupport = inject(AiSupportService);
  private readonly toast = inject(ToastService);
  private readonly route = inject(ActivatedRoute);
  private readonly messagesEl = viewChild<ElementRef<HTMLDivElement>>('messagesEl');

  protected readonly categoryLabels = CATEGORY_LABELS;
  protected readonly faqItems = FAQ_ITEMS;

  protected readonly loading = signal(true);
  protected readonly tickets = signal<SupportTicket[]>([]);
  protected readonly modalOpen = signal(false);
  protected readonly saving = signal(false);

  protected readonly subject = signal('');
  protected readonly category = signal<TicketCategory>('other');
  protected readonly message = signal('');
  protected readonly chatInput = signal('');
  protected readonly supportTyping = signal(false);
  private readonly pendingAction = signal<AiPendingAction | null>(null);
  protected readonly chatMessages = signal<ChatMessage[]>([
    {
      id: 1,
      role: 'support',
      text: 'Bună! Scrie-ne cu ce te putem ajuta — sau alege o întrebare rapidă mai jos.',
      time: formatChatTime(new Date()),
    },
  ]);

  constructor() {
    effect(() => {
      this.chatMessages();
      this.supportTyping();
      const el = this.messagesEl()?.nativeElement;
      if (el) queueMicrotask(() => (el.scrollTop = el.scrollHeight));
    });
  }

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

  protected sendChatMessage(): void {
    const text = this.chatInput().trim();
    if (!text) return;
    this.chatInput.set('');
    this.askAgent(text);
  }

  /** Întrebare rapidă aleasă din lista de sugestii — trimisă ca mesaj real către Support Agent. */
  protected askSuggested(item: { q: string; a: string }): void {
    this.askAgent(item.q);
  }

  /** Trimite un mesaj către Support Agent (backend/ai-orchestrator-service, prin
   * POST /api/ai/support) și afișează răspunsul real. Istoricul conversației e
   * retrimis la fiecare tur (serviciul e stateless) — la fel și `pendingAction`,
   * dacă turul anterior a cerut confirmare pentru o acțiune de scriere (ex.
   * creare tichet de suport); serverul decide dacă mesajul curent e o
   * confirmare validă, nu frontend-ul. */
  private askAgent(text: string): void {
    if (!text || this.supportTyping()) return;

    const history: AiHistoryMessage[] = this.chatMessages().map((m) => ({
      role: m.role === 'support' ? 'assistant' : 'user',
      content: m.text,
    }));
    const pending = this.pendingAction();
    this.pendingAction.set(null);

    this.chatMessages.update((messages) => [
      ...messages,
      { id: Date.now(), role: 'user', text, time: formatChatTime(new Date()) },
    ]);
    this.supportTyping.set(true);

    this.aiSupport.chat({ message: text, history, pending_action: pending }).subscribe({
      next: (response) => {
        this.supportTyping.set(false);
        const context = response.context as ChatContext | undefined;
        this.chatMessages.update((messages) => [
          ...messages,
          {
            id: Date.now() + 1,
            role: 'support',
            text: response.answer,
            time: formatChatTime(new Date()),
            context: context && Object.keys(context).length > 0 ? context : undefined,
          },
        ]);
        const nextPending = response.metadata?.['pending_action'] as AiPendingAction | undefined;
        if (response.requires_confirmation && nextPending) {
          this.pendingAction.set(nextPending);
        }
        if (response.intent === 'support_ticket' && !response.requires_confirmation) {
          this.load(); // tichet creat prin chat — reîmprospătăm "Solicitările mele"
        }
      },
      error: (err) => {
        this.supportTyping.set(false);
        this.toast.error(extractErrorMessage(err, 'Chat-ul de suport nu a putut răspunde. Încearcă din nou.'));
      },
    });
  }

  protected readonly formatChatText = formatChatText;

  /** Transformă flag-urile booleene ale unui card într-o listă afișabilă,
   * ca template-ul să nu itereze direct pe cheile obiectului. */
  protected cardFeatures(card: ChatCardContext): { label: string; enabled: boolean }[] {
    return [
      { label: 'Plăți online', enabled: card.online_payments_enabled },
      { label: 'Contactless', enabled: card.contactless_enabled },
      { label: 'Retrageri ATM', enabled: card.atm_withdrawals_enabled },
      { label: 'Plăți internaționale', enabled: card.international_payments_enabled },
    ];
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
