import { Component, ElementRef, OnDestroy, OnInit, computed, effect, inject, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';

import {
  AiChatMessage as AiHistoryMessage,
  AiPendingAction,
  AiRecommendedAction,
  AiSupportService,
} from '../../services/ai-support.service';
import { SupportService, SupportTicket, TicketCategory } from '../../services/support.service';
import { AccountType } from '../../services/banking.service';
import { SpeechService, stripMarkdownForSpeech } from '../../services/speech.service';
import { LanguageService } from '../../services/language.service';
import { ACCOUNT_TYPE_CATALOG, accountTypeLabel as accountTypeLabelFor } from '../../shared/account-types';
import { SUPPORT_CHAT_STORAGE_KEY } from '../../core/storage-keys';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { ActionButton } from '../../shared/components/action-button/action-button';
import { StatusBadge } from '../../shared/components/status-badge/status-badge';
import { Modal } from '../../shared/components/modal/modal';
import { Icon } from '../../shared/components/icon/icon';
import { ToastService } from '../../shared/components/toast/toast.service';
import { extractErrorMessage } from '../../shared/error-utils';
import { TransactionRow, TransactionRowData } from '../../shared/components/transaction-row/transaction-row';
import { MoneyPipe } from '../../shared/pipes/money.pipe';
import { MarkdownLitePipe } from '../../shared/pipes/markdown-lite.pipe';
import { TranslatePipe } from '../../shared/pipes/translate.pipe';

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
  account_type?: AccountType;
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
  /** TOATE conturile userului (vezi get_my_accounts din
   * app/tools/support_accounts_tools.py) — distinct de `account` (doar
   * contul curent, de la get_my_account). */
  accounts?: ChatAccountContext[];
  tickets?: SupportTicket[];
}

/** Chei i18n (nu text direct) — vezi `faqItems` mai jos, un `computed` care
 * le traduce după limba activă (mirror pe budgets.ts::categoryOptions). */
const FAQ_KEYS: { qKey: string; aKey: string }[] = [
  { qKey: 'support.faqCardFreezeQ', aKey: 'support.faqCardFreezeA' },
  { qKey: 'support.faqTransferQ', aKey: 'support.faqTransferA' },
  { qKey: 'support.faqTransactionQ', aKey: 'support.faqTransactionA' },
  { qKey: 'support.faqExchangeQ', aKey: 'support.faqExchangeA' },
];

interface ChatMessage {
  id: number;
  role: 'support' | 'user';
  text: string;
  time: string;
  context?: ChatContext;
  /** Sugestii de follow-up ale agentului (vezi respond_to_user::recommended_actions
   * din app/agents/support.py) — populate de GPT, NU doar text irosit: un
   * click retrimite eticheta ca mesaj nou, exact ca o întrebare rapidă. */
  recommendedActions?: AiRecommendedAction[];
}

function formatChatTime(date: Date): string {
  return date.toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' });
}

// Conversația se ține minte între vizite (refresh, navigare și înapoi) —
// persistată în `sessionStorage` (ca JWT-ul, vezi AuthService), NU
// `localStorage`: dispare la închiderea tab-ului, nu rămâne pe disc la
// nesfârșit. Ștearsă explicit la logout (vezi AuthService.logout()), ca
// userul următor de pe același tab să nu vadă conversația celui dinainte.
// Backend-ul e tot stateless — istoricul persistat AICI e cel retrimis la
// fiecare mesaj (vezi askAgent), plafonat server-side oricum (vezi
// app/agents/support.py::_MAX_HISTORY_MESSAGES). Cap generos, DOAR pentru
// spațiul de stocare local (transcriptul vizibil poate fi mai lung decât
// ce se retrimite efectiv ca `history`).
const _MAX_PERSISTED_MESSAGES = 100;

function loadPersistedMessages(): ChatMessage[] {
  try {
    const raw = sessionStorage.getItem(SUPPORT_CHAT_STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as ChatMessage[]) : [];
  } catch {
    // Date corupte/format vechi — pornim curat, nu blocăm pagina.
    return [];
  }
}

function persistMessages(messages: ChatMessage[]): void {
  try {
    sessionStorage.setItem(SUPPORT_CHAT_STORAGE_KEY, JSON.stringify(messages.slice(-_MAX_PERSISTED_MESSAGES)));
  } catch {
    // sessionStorage plin/indisponibil (mod privat etc.) — chat-ul tot
    // funcționează în pagina curentă, doar nu supraviețuiește unui refresh.
  }
}

/**
 * Support — chat live cu Support Agent (ai-orchestrator-service, prin
 * Gateway — vezi services/ai-support.service.ts). Vizual, aceeași familie
 * cu MaestroAssistent (vezi features/copilot) — bule/carduri, avatar +
 * nume + oră pe fiecare mesaj, markdown-lite pentru text — dar funcțional
 * diferit: Support Agent răspunde despre cont/card/tranzacții/tichete (NU
 * forecast/buget, vezi app/prompts/support_prompt.py), iar aici mai
 * există și FAQ + un formular de solicitare nouă, pe care MaestroAssistent
 * nu le are (fără o listă persistentă a solicitărilor trimise — la
 * cererea userului).
 */
@Component({
  selector: 'app-support',
  standalone: true,
  imports: [FormsModule, MoneyPipe, MarkdownLitePipe, PageHeader, ActionButton, StatusBadge, Modal, Icon, TransactionRow, TranslatePipe],
  templateUrl: './support.html',
  styleUrl: './support.css',
})
export class Support implements OnInit, OnDestroy {
  private readonly supportApi = inject(SupportService);
  private readonly aiSupport = inject(AiSupportService);
  protected readonly speech = inject(SpeechService);
  private readonly toast = inject(ToastService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly language = inject(LanguageService);
  private readonly messagesEl = viewChild<ElementRef<HTMLDivElement>>('messagesEl');

  protected readonly faqItems = computed(() => FAQ_KEYS.map((k) => ({ q: this.language.t(k.qKey), a: this.language.t(k.aKey) })));

  protected readonly modalOpen = signal(false);
  protected readonly saving = signal(false);

  protected readonly subject = signal('');
  protected readonly category = signal<TicketCategory>('other');
  protected readonly message = signal('');
  protected readonly chatInput = signal('');
  protected readonly supportTyping = signal(false);
  /** Adevărat doar dacă răspunsul curent durează mai mult decât normal
   * (vezi timeout-ul de pe backend, app/llm/azure_openai.py) — ca userul
   * să știe că nu s-a blocat, doar durează mai mult ca de obicei. */
  protected readonly supportTypingSlow = signal(false);
  private slowTimer?: ReturnType<typeof setTimeout>;
  private readonly pendingAction = signal<AiPendingAction | null>(null);
  /** Reia conversația din `sessionStorage`, dacă există (vezi
   * loadPersistedMessages mai sus) — gol doar la prima vizită din tab-ul
   * ăsta, caz în care arată ecranul de bun-venit cu sugestii, nu un mesaj
   * seedat static (ca MaestroAssistent — vezi features/copilot/copilot.ts). */
  protected readonly chatMessages = signal<ChatMessage[]>(loadPersistedMessages());

  constructor() {
    effect(() => {
      this.chatMessages();
      this.supportTyping();
      const el = this.messagesEl()?.nativeElement;
      if (el) queueMicrotask(() => (el.scrollTop = el.scrollHeight));
    });

    // Persistă conversația la fiecare schimbare — separat de efectul de
    // mai sus (ăla mai reacționează și la `supportTyping`, ceea ce ar
    // însemna scrieri inutile în sessionStorage la fiecare tick de "scrie...").
    effect(() => {
      persistMessages(this.chatMessages());
    });
  }

  ngOnInit(): void {
    const shouldOpen = this.route.snapshot.queryParamMap.get('newTicket') === '1';
    const presetCategory = this.route.snapshot.queryParamMap.get('category') as TicketCategory | null;
    if (presetCategory) this.category.set(presetCategory);
    if (shouldOpen) this.openModal();
  }

  ngOnDestroy(): void {
    // Nu lăsăm vocea să continue să citească un mesaj după ce userul a
    // plecat de pe pagină — vezi Copilot::ngOnDestroy, același motiv.
    this.speech.stopSpeaking();
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

  /** Microfon — vezi Copilot::toggleListening, exact același comportament
   * (textul recunoscut apare în input, nu se trimite automat). */
  protected toggleListening(): void {
    if (this.speech.listening()) {
      this.speech.stopListening();
      return;
    }
    this.speech.startListening((text) => {
      if (text) this.chatInput.set(text);
    });
  }

  /** "Ascultă" pe un răspuns al Support Agent — vezi Copilot::toggleSpeak. */
  protected toggleSpeak(chatMessage: ChatMessage): void {
    if (this.speech.speakingMessageId() === chatMessage.id) {
      this.speech.stopSpeaking();
      return;
    }
    this.speech.speak(stripMarkdownForSpeech(chatMessage.text), chatMessage.id);
  }

  /** Întrebare rapidă aleasă din lista de sugestii — trimisă ca mesaj real către Support Agent. */
  protected askSuggested(item: { q: string; a: string }): void {
    this.askAgent(item.q);
  }

  /** Acțiune recomandată de agent (vezi ChatMessage.recommendedActions).
   * Dacă are `route` (rezolvată determinist de backend, NU de GPT — vezi
   * ai-support.service.ts), navighează REAL la pagina aia. Altfel (ex.
   * "view_tickets"), retrimite eticheta ca mesaj nou, la fel ca o
   * întrebare rapidă. */
  protected runRecommendedAction(action: AiRecommendedAction): void {
    if (action.route) {
      this.router.navigateByUrl(action.route);
      return;
    }
    this.askAgent(action.label);
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
    this.supportTypingSlow.set(false);
    // Majoritatea răspunsurilor vin în 10-20s (tool-calling GPT-5-mini) —
    // dacă trece mai mult, arătăm un indiciu, ca să nu pară că s-a blocat.
    this.slowTimer = setTimeout(() => this.supportTypingSlow.set(true), 15_000);

    this.aiSupport.chat({ message: text, history, pending_action: pending }).subscribe({
      next: (response) => {
        this.stopTyping();
        const context = response.context as ChatContext | undefined;
        this.chatMessages.update((messages) => [
          ...messages,
          {
            id: Date.now() + 1,
            role: 'support',
            text: response.answer,
            time: formatChatTime(new Date()),
            context: context && Object.keys(context).length > 0 ? context : undefined,
            recommendedActions: response.recommended_actions.length > 0 ? response.recommended_actions : undefined,
          },
        ]);
        const nextPending = response.metadata?.['pending_action'] as AiPendingAction | undefined;
        if (response.requires_confirmation && nextPending) {
          this.pendingAction.set(nextPending);
        }
      },
      error: (err) => {
        this.stopTyping();
        this.toast.error(extractErrorMessage(err, this.language.t('support.chatError')));
      },
    });
  }

  private stopTyping(): void {
    this.supportTyping.set(false);
    this.supportTypingSlow.set(false);
    clearTimeout(this.slowTimer);
  }

  /** Eticheta reală a unui tip de cont (ex. "Cont de economii") — REFOLOSEȘTE
   * catalogul din pagina Conturi (shared/account-types.ts), ca eticheta din
   * chat să fie mereu identică cu ce vede userul acolo, niciodată inventată. */
  protected accountTypeLabel(type: AccountType | undefined): string {
    return type ? accountTypeLabelFor(ACCOUNT_TYPE_CATALOG[type], this.language.language()) : this.language.t('support.genericAccount');
  }

  /** Transformă flag-urile booleene ale unui card într-o listă afișabilă,
   * ca template-ul să nu itereze direct pe cheile obiectului. */
  protected cardFeatures(card: ChatCardContext): { label: string; enabled: boolean }[] {
    return [
      { label: this.language.t('support.onlinePayments'), enabled: card.online_payments_enabled },
      { label: this.language.t('support.contactless'), enabled: card.contactless_enabled },
      { label: this.language.t('support.atmWithdrawals'), enabled: card.atm_withdrawals_enabled },
      { label: this.language.t('support.internationalPayments'), enabled: card.international_payments_enabled },
    ];
  }

  protected submitTicket(): void {
    if (!this.subject().trim() || !this.message().trim()) {
      this.toast.error(this.language.t('support.fillSubjectAndMessage'));
      return;
    }
    this.saving.set(true);
    this.supportApi
      .createTicket({ subject: this.subject().trim(), category: this.category(), message: this.message().trim() })
      .subscribe({
        next: () => {
          this.saving.set(false);
          this.modalOpen.set(false);
          this.toast.success(this.language.t('support.ticketSubmitted'));
        },
        error: (err) => {
          this.saving.set(false);
          this.toast.error(extractErrorMessage(err, this.language.t('support.submitTicketError')));
        },
      });
  }
}
