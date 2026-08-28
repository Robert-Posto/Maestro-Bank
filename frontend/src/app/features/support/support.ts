import { Component, ElementRef, HostListener, OnDestroy, OnInit, computed, effect, inject, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';

import { DatePipe } from '@angular/common';

import {
  AiPendingAction,
  AiRecommendedAction,
  AiSupportService,
  ConversationDetail,
  ConversationSummary,
} from '../../services/ai-support.service';
import { AiCopilotService, SpendingForecastResponse } from '../../services/ai-copilot.service';
import { AssistantService } from '../../services/assistant.service';
import { SupportService, SupportTicket, TicketCategory } from '../../services/support.service';
import { AccountType } from '../../services/banking.service';
import { SpeechService, stripMarkdownForSpeech } from '../../services/speech.service';
import { LanguageService } from '../../services/language.service';
import { ACCOUNT_TYPE_CATALOG, accountTypeLabel as accountTypeLabelFor } from '../../shared/account-types';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { ActionButton } from '../../shared/components/action-button/action-button';
import { StatusBadge } from '../../shared/components/status-badge/status-badge';
import { Modal } from '../../shared/components/modal/modal';
import { Icon } from '../../shared/components/icon/icon';
import { Select, SelectOption } from '../../shared/components/select/select';
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
 * le traduce după limba activă (mirror pe budgets.ts::categoryOptions).
 * Ultimele două țin de fapt de MaestroAgent (buget/prognoză), nu de Support
 * — apar aici intenționat, ca userul să vadă din prima că poate întreba
 * orice și e redirecționat automat (vezi askAgent, care clasifică primul
 * mesaj al unei conversații noi). */
const FAQ_KEYS: { qKey: string; aKey: string }[] = [
  { qKey: 'support.faqCardFreezeQ', aKey: 'support.faqCardFreezeA' },
  { qKey: 'support.faqTransferQ', aKey: 'support.faqTransferA' },
  { qKey: 'support.faqTransactionQ', aKey: 'support.faqTransactionA' },
  { qKey: 'support.faqExchangeQ', aKey: 'support.faqExchangeA' },
  { qKey: 'support.faqAffordQ', aKey: 'support.faqAffordA' },
  { qKey: 'support.faqSpentQ', aKey: 'support.faqSpentA' },
];

/** Cuvinte care se rotesc cât timp agentul lucrează — vezi
 * copilot.ts, același concept (jocuri de cuvinte, stil Claude), set pe
 * limbă (vezi `thinkingWords()`). Două seturi diferite — unul per agent —
 * fiindcă acum AMBII agenți răspund pe ACEEAȘI pagină (vezi askAgent), nu
 * doar Support ca înainte. */
const SUPPORT_THINKING_WORDS_RO = ['Maestroing', 'Detectivind', 'Răscolind', 'Percolând', 'Investigând', 'Chibzuind'];
const SUPPORT_THINKING_WORDS_EN = ['Maestroing', 'Sleuthing', 'Digging', 'Percolating', 'Investigating', 'Mulling'];
const MAESTRO_THINKING_WORDS_RO = ['Maestroing', 'Bănuind', 'Cifrometrând', 'Leuind', 'Buzunărind', 'Chibzuind'];
const MAESTRO_THINKING_WORDS_EN = ['Maestroing', 'Pondering', 'Number-crunching', 'Tallying', 'Rummaging', 'Mulling'];

/** Vezi Copilot::confirmPendingAction — starea butonului de confirmare
 * pentru o acțiune de buget PROPUSĂ de MaestroAgent (create/update/delete
 * budget), distinctă de `AiPendingAction` (confirmarea Support Agent,
 * text-based, pentru crearea unui tichet). Cei doi agenți au fluxuri de
 * confirmare COMPLET separate — nu se amestecă niciodată. */
type MaestroActionState = 'pending' | 'confirming' | 'done' | 'cancelled' | 'error';

interface ChatMessage {
  id: number;
  role: 'support' | 'maestro' | 'user';
  text: string;
  time: string;
  context?: ChatContext;
  /** Sugestii de follow-up ale agentului (vezi respond_to_user::recommended_actions
   * din app/agents/support.py) — populate de GPT, NU doar text irosit: un
   * click retrimite eticheta ca mesaj nou, exact ca o întrebare rapidă. */
  recommendedActions?: AiRecommendedAction[];
  /** Doar pentru role: 'maestro' — răspunsul bogat al agentului Spending +
   * Forecast (carduri de analiză/prognoză, buget, acțiune propusă). */
  maestroResponse?: SpendingForecastResponse;
  maestroActionState?: MaestroActionState;
  maestroActionResultText?: string;
  errorText?: string;
}

function formatChatTime(date: Date): string {
  return date.toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' });
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
  imports: [FormsModule, DatePipe, MoneyPipe, MarkdownLitePipe, PageHeader, ActionButton, StatusBadge, Modal, Icon, Select, TransactionRow, TranslatePipe],
  templateUrl: './support.html',
  styleUrl: './support.css',
})
export class Support implements OnInit, OnDestroy {
  private readonly supportApi = inject(SupportService);
  private readonly aiSupport = inject(AiSupportService);
  private readonly aiCopilot = inject(AiCopilotService);
  private readonly assistant = inject(AssistantService);
  protected readonly speech = inject(SpeechService);
  private readonly toast = inject(ToastService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly language = inject(LanguageService);
  private readonly messagesEl = viewChild<ElementRef<HTMLDivElement>>('messagesEl');
  private readonly conversationsMenuEl = viewChild<ElementRef<HTMLDivElement>>('conversationsMenuEl');

  protected readonly faqItems = computed(() => FAQ_KEYS.map((k) => ({ q: this.language.t(k.qKey), a: this.language.t(k.aKey) })));

  protected readonly modalOpen = signal(false);
  protected readonly saving = signal(false);

  protected readonly subject = signal('');
  protected readonly category = signal<TicketCategory>('other');
  /** app-select în loc de <select> nativ — vezi budgets.ts::periodOptions,
   * același motiv (popup-ul nativ ignoră tokenii --mb-*, rupe dark mode). */
  protected readonly categoryOptions = computed<SelectOption[]>(() => {
    this.language.language();
    return [
      { value: 'card', label: this.language.t('support.categoryCard') },
      { value: 'transfer', label: this.language.t('support.categoryTransfer') },
      { value: 'account', label: this.language.t('support.categoryAccount') },
      { value: 'technical', label: this.language.t('support.categoryTechnical') },
      { value: 'other', label: this.language.t('support.categoryOther') },
    ];
  });
  protected setCategory(value: string): void {
    this.category.set(value as TicketCategory);
  }
  protected readonly message = signal('');
  protected readonly chatInput = signal('');
  protected readonly supportTyping = signal(false);
  /** Adevărat doar dacă răspunsul curent durează mai mult decât normal
   * (vezi timeout-ul de pe backend, app/llm/azure_openai.py) — ca userul
   * să știe că nu s-a blocat, doar durează mai mult ca de obicei. */
  protected readonly supportTypingSlow = signal(false);
  protected readonly thinkingWord = signal(SUPPORT_THINKING_WORDS_RO[0]);
  /** Care agent e "pe fir" cât timp `supportTyping()` e true — determină ce
   * cuvinte de "gândește" și ce nume arătăm în indicatorul de typing (vezi
   * support.html). Nu mai navigăm către o pagină separată pentru
   * MaestroAgent (cerut explicit de user: "lasam tot pe pagina mare, nu ne
   * mai invartim"), deci indicatorul de typing trebuie să reflecte agentul
   * REAL care lucrează, nu presupune mereu Support. */
  protected readonly awaitingAgent = signal<'support' | 'maestro'>('support');
  private slowTimer?: ReturnType<typeof setTimeout>;
  private thinkingWordTimer?: ReturnType<typeof setInterval>;

  /** Setul de cuvinte "gândește" pentru limba activă + agentul curent. */
  private thinkingWords(): string[] {
    const en = this.language.language() === 'en';
    if (this.awaitingAgent() === 'maestro') return en ? MAESTRO_THINKING_WORDS_EN : MAESTRO_THINKING_WORDS_RO;
    return en ? SUPPORT_THINKING_WORDS_EN : SUPPORT_THINKING_WORDS_RO;
  }
  private readonly pendingAction = signal<AiPendingAction | null>(null);
  /** Gol doar la prima vizită/conversație nouă — caz în care arată ecranul
   * de bun-venit cu sugestii, nu un mesaj seedat static (ca MaestroAssistent
   * — vezi features/copilot/copilot.ts). */
  protected readonly chatMessages = signal<ChatMessage[]>([]);
  protected readonly conversations = signal<ConversationSummary[]>([]);
  protected readonly activeConversationId = signal<string | null>(null);
  /** Conversația MaestroAgent, SEPARATĂ de cea de Support — cei doi agenți
   * au propriile colecții de conversații persistate pe backend (fiecare cu
   * propriul `agent` field), deci nu pot împărți un singur ID. Vizual, pe
   * pagina asta, turele lor apar totuși în ACEEAȘI listă continuă
   * (`chatMessages`) — doar id-ul de conversație trimis la backend diferă
   * în funcție de care agent răspunde la turul curent. */
  protected readonly maestroConversationId = signal<string | null>(null);
  protected readonly conversationsMenuOpen = signal(false);

  /** Titlul afișat pe trigger-ul dropdown-ului de conversații — vezi
   * Copilot::activeConversationTitle, același comportament. */
  protected readonly activeConversationTitle = computed(() => {
    const id = this.activeConversationId();
    if (!id) return this.language.t('support.newConversation');
    return this.conversations().find((c) => c.id === id)?.title ?? this.language.t('support.newConversation');
  });

  /** Adevărat doar după ce a existat DEJA cel puțin un tur (Support SAU
   * MaestroAgent — vezi lastAnsweringAgent mai jos). Înainte de primul
   * mesaj identitatea rămâne generică ("Asistent"), fiindcă întrebarea
   * încă n-a fost clasificată. Folosit și în template (vezi support.html),
   * de-aia e protected, nu private. */
  protected readonly hasStartedConversation = computed(() => this.chatMessages().length > 0);

  /** Care agent a răspuns ULTIMUL — determină identitatea afișată sus
   * (titlu + bara de identitate a chat-ului). Ambii agenți răspund acum pe
   * ACEEAȘI pagină, fără navigare (vezi askAgent) — userul cere explicit
   * doar să i se spună care agent lucrează, nu să fie plimbat între
   * pagini. `undefined` înainte de primul răspuns. */
  protected readonly lastAnsweringAgent = computed<'support' | 'maestro' | undefined>(() => {
    const messages = this.chatMessages();
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'support') return 'support';
      if (messages[i].role === 'maestro') return 'maestro';
    }
    return undefined;
  });

  /** Titlul de sus al paginii (PageHeader, doar text — vezi
   * support.html pentru săgeata REALĂ, ca iconiță, din bara de
   * identitate a chat-ului, care nu poate exista aici, PageHeader
   * acceptă doar string). */
  protected readonly pageTitle = computed(() => {
    const agent = this.lastAnsweringAgent();
    if (agent === 'maestro') return this.language.t('copilot.breadcrumbTitle');
    if (agent === 'support') return this.language.t('support.breadcrumbTitle');
    return this.language.t('nav.assistant');
  });

  protected readonly identitySubtitle = computed(() => {
    const agent = this.lastAnsweringAgent();
    if (agent === 'maestro') return this.language.t('copilot.identitySubtitle');
    if (agent === 'support') return this.language.t('support.identitySubtitle');
    return this.language.t('support.identitySubtitleGeneric');
  });
  /** MaestroAgent și starea generică (pre-clasificare) folosesc amândouă
   * "sparkles" — doar Support are propria iconiță distinctă. */
  protected readonly identityIcon = computed(() => (this.lastAnsweringAgent() === 'support' ? 'support' : 'sparkles'));

  constructor() {
    effect(() => {
      this.chatMessages();
      this.supportTyping();
      const el = this.messagesEl()?.nativeElement;
      if (el) queueMicrotask(() => (el.scrollTop = el.scrollHeight));
    });
  }

  ngOnInit(): void {
    this.loadConversations();
    const shouldOpen = this.route.snapshot.queryParamMap.get('newTicket') === '1';
    const presetCategory = this.route.snapshot.queryParamMap.get('category') as TicketCategory | null;
    if (presetCategory) this.category.set(presetCategory);
    if (shouldOpen) this.openModal();

    // Venit prin butonul "Înapoi la Asistent" de pe MaestroAgent (vezi
    // copilot.ts::backToMainAgent) — pornim explicit o conversație nouă,
    // ca prima întrebare de-aici să fie reclasificată de la zero (vezi
    // askAgent mai jos: clasificarea rulează doar la prima tură a unei
    // conversații NOI). Fără asta, dacă rămăsese activă o conversație
    // veche de Support, userul ar fi "blocat" acolo chiar dacă a apăsat
    // explicit "înapoi" ca să întrebe altceva.
    if (this.route.snapshot.queryParamMap.get('fresh') === '1') {
      this.startNewConversation();
      this.router.navigate([], { relativeTo: this.route, queryParams: {}, replaceUrl: true });
    }
  }

  ngOnDestroy(): void {
    // Nu lăsăm vocea să continue să citească un mesaj după ce userul a
    // plecat de pe pagină — vezi Copilot::ngOnDestroy, același motiv.
    this.speech.stopSpeaking();
    clearInterval(this.thinkingWordTimer);
  }

  private loadConversations(): void {
    this.aiSupport.listConversations().subscribe({
      next: (list) => this.conversations.set(list),
    });
  }

  protected toggleConversationsMenu(): void {
    this.conversationsMenuOpen.update((open) => !open);
  }

  @HostListener('document:click', ['$event'])
  protected onDocumentClick(event: MouseEvent): void {
    if (!this.conversationsMenuOpen()) return;
    const menu = this.conversationsMenuEl()?.nativeElement;
    if (menu && !menu.contains(event.target as Node)) {
      this.conversationsMenuOpen.set(false);
    }
  }

  protected startNewConversation(): void {
    this.conversationsMenuOpen.set(false);
    this.activeConversationId.set(null);
    this.maestroConversationId.set(null);
    this.pendingAction.set(null);
    this.chatMessages.set([]);
  }

  protected openConversation(id: string): void {
    this.conversationsMenuOpen.set(false);
    if (id === this.activeConversationId()) return;
    this.aiSupport.getConversation(id).subscribe({
      next: (detail: ConversationDetail) => {
        this.activeConversationId.set(detail.id);
        // O conversație salvată e mereu 100% Support (istoricul persistat
        // separat pe backend — vezi maestroConversationId mai sus), deci
        // orice fir de Maestro rămas dintr-o sesiune anterioară nu mai are
        // sens aici.
        this.maestroConversationId.set(null);
        this.pendingAction.set(null);
        this.chatMessages.set(
          detail.messages.map((m, index) => {
            const response = m.response;
            const context = response?.context as ChatContext | undefined;
            return {
              id: index,
              role: m.role === 'assistant' ? 'support' : 'user',
              text: m.content,
              time: formatChatTime(new Date(m.created_at)),
              context: context && Object.keys(context).length > 0 ? context : undefined,
              recommendedActions:
                response?.recommended_actions && response.recommended_actions.length > 0
                  ? response.recommended_actions
                  : undefined,
            };
          }),
        );
      },
      error: (err) => this.toast.error(extractErrorMessage(err, this.language.t('support.loadConversationError'))),
    });
  }

  protected deleteConversation(event: Event, id: string): void {
    event.stopPropagation();
    this.aiSupport.deleteConversation(id).subscribe({
      next: () => {
        this.conversations.update((list) => list.filter((c) => c.id !== id));
        if (this.activeConversationId() === id) this.startNewConversation();
      },
      error: (err) => this.toast.error(extractErrorMessage(err, this.language.t('support.deleteConversationError'))),
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

  /** Trimite un mesaj către agentul potrivit — Support SAU MaestroAgent,
   * decis de classify() la fiecare mesaj nou, dar AMÂNDOI răspund pe
   * ACEEAȘI pagină, în ACEEAȘI listă de mesaje (`chatMessages`) — nu mai
   * navigăm niciodată către o pagină separată pentru MaestroAgent (cerut
   * explicit de user: "lasam tot pe pagina mare... doar mentionam ce agent
   * e folosit"). Istoricul fiecărui agent e retrimis la fiecare tur al LUI
   * (fiecare are propriul `conversation_id`, vezi activeConversationId vs
   * maestroConversationId) — la fel și `pendingAction`, dacă turul anterior
   * de Support a cerut confirmare pentru o acțiune de scriere (ex. creare
   * tichet); serverul decide dacă mesajul curent e o confirmare validă,
   * nu frontend-ul. */
  private askAgent(text: string): void {
    if (!text || this.supportTyping()) return;

    // Bula userului apare INSTANT, indiferent de ce urmează — clasificarea
    // de mai jos poate însemna acum un apel LLM (nu mai e mereu instantă,
    // ca înainte cu doar regex), deci FĂRĂ asta userul ar vedea ecranul
    // "înghețat" un moment, fără nicio confirmare că mesajul chiar a
    // plecat (bug raportat: "nu-mi apare imediat mesajul meu pe interfață").
    this.chatMessages.update((messages) => [
      ...messages,
      { id: Date.now(), role: 'user', text, time: formatChatTime(new Date()) },
    ]);

    // La FIECARE mesaj nou (nu doar primul al unei conversații noi),
    // verificăm dacă întrebarea ține de fapt de MaestroAgent (buget/
    // prognoză/economii/abonamente — vezi intent_router.py din backend,
    // acum clasificare hibridă: cuvinte-cheie + fallback LLM, nu doar
    // regex) și, dacă da, îi răspundem AICI, fără nicio navigare.
    // Excepție: un mesaj care confirmă o acțiune de Support în curs
    // (pendingAction, ex. "da" pentru crearea unui tichet) NU se
    // reclasifică niciodată — nu e o întrebare nouă, e un răspuns la ceva
    // deja pus.
    if (!this.pendingAction()) {
      // Dezactivează inputul (vezi [disabled]="supportTyping()" în
      // support.html) cât timp se decide agentul — previne un al doilea
      // Trimite în timp ce clasificarea e în curs.
      this.supportTyping.set(true);

      this.assistant.classify(text).subscribe({
        next: (result) => {
          if (result.agent === 'spending_forecast') {
            // Toast-ul are sens DOAR la PRIMA implicare a AGENTULUI ĂSTUIA
            // în conversație — verificăm `maestroConversationId` (populat
            // abia după primul răspuns real de-al lui, vezi askMaestroAgent),
            // NU `chatMessages().length` (deja nenul aici, bula userului a
            // fost pusă mai sus) și NICI starea lui Support — dacă
            // MaestroAgent preia pentru prima oară o conversație pornită
            // deja cu Support, tot merită anunțat, nu doar la mesajul 1.
            if (!this.maestroConversationId()) {
              this.toast.info(this.language.t('support.answeredByMaestroAgent'));
            }
            this.askMaestroAgent(text, true);
          } else {
            if (!this.activeConversationId()) {
              this.toast.info(this.language.t('support.answeredBySupport'));
            }
            this.sendToSupportAgent(text, true);
          }
        },
        // Clasificarea eșuată (ex. serviciul indisponibil) NU trebuie să
        // blocheze conversația — Support e deja domeniul implicit/catch-all.
        error: () => this.sendToSupportAgent(text, true),
      });
      return;
    }

    this.sendToSupportAgent(text, true);
  }

  /** Trimite un mesaj către MaestroAgent (Spending + Forecast, backend/
   * ai-orchestrator-service, prin POST /api/ai/spending-forecast/chat) —
   * vezi Copilot::ask, aceeași logică, dar scriind în `chatMessages`-ul
   * ACESTEI pagini (role: 'maestro'), nu într-o pagină separată. */
  private askMaestroAgent(text: string, userBubbleAlreadyShown = false): void {
    if (!userBubbleAlreadyShown) {
      this.chatMessages.update((messages) => [
        ...messages,
        { id: Date.now(), role: 'user', text, time: formatChatTime(new Date()) },
      ]);
    }
    this.awaitingAgent.set('maestro');
    this.supportTyping.set(true);
    this.supportTypingSlow.set(false);
    this.slowTimer = setTimeout(() => this.supportTypingSlow.set(true), 15_000);
    this.startThinkingWords();

    this.aiCopilot.sendMessage(text, this.maestroConversationId()).subscribe({
      next: (response) => {
        this.stopTyping();
        if (!this.maestroConversationId()) {
          this.maestroConversationId.set(response.conversation_id);
        }
        this.chatMessages.update((messages) => [
          ...messages,
          {
            id: Date.now() + 1,
            role: 'maestro',
            text: response.answer,
            time: formatChatTime(new Date()),
            maestroResponse: response,
            maestroActionState: response.pending_action ? 'pending' : undefined,
          },
        ]);
      },
      error: (err) => {
        this.stopTyping();
        this.chatMessages.update((messages) => [
          ...messages,
          {
            id: Date.now() + 1,
            role: 'maestro',
            text: '',
            time: formatChatTime(new Date()),
            errorText: extractErrorMessage(err, this.language.t('copilot.errorFallback')),
          },
        ]);
      },
    });
  }

  /** Execută REAL acțiunea de buget propusă de MaestroAgent — vezi
   * Copilot::confirmPendingAction, identic, doar scriind în ChatMessage-ul
   * de-aici (maestroActionState, nu actionState — flux complet separat de
   * pendingAction-ul Support Agent, vezi tipul MaestroActionState). */
  protected confirmMaestroPendingAction(message: ChatMessage): void {
    const action = message.maestroResponse?.pending_action;
    if (!action || message.maestroActionState !== 'pending') return;

    this.updateMaestroActionState(message.id, 'confirming');
    this.aiCopilot.confirmAction(action).subscribe({
      next: (result) => {
        this.updateMaestroActionState(message.id, result.success ? 'done' : 'error', result.message);
      },
      error: (err) => {
        const errorText = extractErrorMessage(err, this.language.t('copilot.actionErrorFallback'));
        this.updateMaestroActionState(message.id, 'error', errorText);
      },
    });
  }

  protected cancelMaestroPendingAction(message: ChatMessage): void {
    if (message.maestroActionState !== 'pending') return;
    this.updateMaestroActionState(message.id, 'cancelled');
  }

  private updateMaestroActionState(messageId: number, state: MaestroActionState, resultText?: string): void {
    this.chatMessages.update((messages) =>
      messages.map((m) => (m.id === messageId ? { ...m, maestroActionState: state, maestroActionResultText: resultText } : m)),
    );
  }

  /** Vezi Copilot::sourceLabels — etichete scurte, prietenoase pentru
   * documentele RAG folosite de MaestroAgent. */
  protected maestroSourceLabels(sources: { source: string }[]): string {
    return sources.map((s) => s.source.replace(/\.md$/, '').replace(/_/g, ' ')).join(', ');
  }

  /** `userBubbleAlreadyShown` — adevărat când askAgent a afișat deja bula
   * userului (cazul normal, vezi mai sus); fals DOAR când sendToSupportAgent
   * ar fi apelat direct, din afara askAgent (nu mai există azi un astfel de
   * apelant, dar parametrul rămâne explicit, nu implicit, ca să nu se piardă
   * din vedere dacă apare unul nou). */
  private sendToSupportAgent(text: string, userBubbleAlreadyShown = false): void {
    const pending = this.pendingAction();
    this.pendingAction.set(null);
    this.awaitingAgent.set('support');

    if (!userBubbleAlreadyShown) {
      this.chatMessages.update((messages) => [
        ...messages,
        { id: Date.now(), role: 'user', text, time: formatChatTime(new Date()) },
      ]);
    }
    this.supportTyping.set(true);
    this.supportTypingSlow.set(false);
    // Majoritatea răspunsurilor vin în 10-20s (tool-calling GPT-5-mini) —
    // dacă trece mai mult, arătăm un indiciu, ca să nu pară că s-a blocat.
    this.slowTimer = setTimeout(() => this.supportTypingSlow.set(true), 15_000);
    this.startThinkingWords();

    this.aiSupport.chat({ message: text, conversation_id: this.activeConversationId(), pending_action: pending }).subscribe({
      next: (response) => {
        this.stopTyping();
        if (!this.activeConversationId()) {
          this.activeConversationId.set(response.conversation_id);
          this.loadConversations();
        }
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
    clearInterval(this.thinkingWordTimer);
  }

  /** Vezi Copilot::startThinkingWords, același comportament. */
  private startThinkingWords(): void {
    const words = this.thinkingWords();
    this.thinkingWord.set(words[Math.floor(Math.random() * words.length)]);
    this.thinkingWordTimer = setInterval(() => {
      this.thinkingWord.update((current) => {
        const options = this.thinkingWords().filter((w) => w !== current);
        return options[Math.floor(Math.random() * options.length)];
      });
    }, 1800);
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
