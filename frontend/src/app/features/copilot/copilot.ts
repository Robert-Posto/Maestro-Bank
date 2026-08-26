import { Component, ElementRef, OnDestroy, OnInit, computed, effect, inject, signal, viewChild } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { AiCopilotService, ConversationDetail, ConversationSummary, SpendingForecastResponse } from '../../services/ai-copilot.service';
import { SpeechService, stripMarkdownForSpeech } from '../../services/speech.service';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { Icon } from '../../shared/components/icon/icon';
import { MoneyPipe } from '../../shared/pipes/money.pipe';
import { MarkdownLitePipe } from '../../shared/pipes/markdown-lite.pipe';
import { extractErrorMessage } from '../../shared/error-utils';
import { ToastService } from '../../shared/components/toast/toast.service';

const SUGGESTED_QUESTIONS = [
  'Îmi permit un city break de 2.000 lei luna asta?',
  'Cât am cheltuit luna asta?',
  'Cu cât estimezi că rămân la finalul lunii?',
  'Pe ce categorie cheltuiesc cel mai mult?',
];

type PendingActionState = 'pending' | 'confirming' | 'done' | 'cancelled' | 'error';

interface ChatMessage {
  id: number;
  role: 'assistant' | 'user';
  text: string;
  time: string;
  response?: SpendingForecastResponse;
  errorText?: string;
  /** Doar pentru mesaje assistant cu `response.pending_action` — starea
   * butonului de confirmare (vezi confirmPendingAction/cancelPendingAction). */
  actionState?: PendingActionState;
  actionResultText?: string;
}

function formatChatTime(date: Date): string {
  return date.toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' });
}

/**
 * MaestroAssistent — conectat la ai-orchestrator-service (agentul Spending
 * + Forecast), prin Gateway (vezi services/ai-copilot.service.ts). Un
 * răspuns implică tool-calling real către GPT-5-mini, deci poate dura
 * 10-20s — de-aia starea "se gândește" e vizibilă, nu doar un spinner sec.
 *
 * Support Agent (celălalt agent găzduit de ai-orchestrator-service) e
 * conectat la pagina Suport (vezi features/support/support.ts), NU aici.
 */
@Component({
  selector: 'app-copilot',
  standalone: true,
  imports: [FormsModule, DatePipe, PageHeader, Icon, MoneyPipe, MarkdownLitePipe],
  templateUrl: './copilot.html',
  styleUrl: './copilot.css',
})
export class Copilot implements OnInit, OnDestroy {
  private readonly copilotApi = inject(AiCopilotService);
  protected readonly speech = inject(SpeechService);
  private readonly toast = inject(ToastService);
  private readonly messagesEl = viewChild<ElementRef<HTMLDivElement>>('messagesEl');

  protected readonly suggestedQuestions = SUGGESTED_QUESTIONS;
  protected readonly chatInput = signal('');
  protected readonly sending = signal(false);
  /** Adevărat doar dacă răspunsul curent durează mai mult decât normal
   * (vezi timeout-ul de pe backend, app/llm/azure_openai.py) — ca userul
   * să știe că nu s-a blocat, doar durează mai mult ca de obicei. */
  protected readonly sendingSlow = signal(false);
  protected readonly chatMessages = signal<ChatMessage[]>([]);
  protected readonly conversations = signal<ConversationSummary[]>([]);
  protected readonly activeConversationId = signal<string | null>(null);
  private slowTimer?: ReturnType<typeof setTimeout>;

  /** Ultimul răspuns reușit — alimentează "Context financiar" din sidebar,
   * ca să rămână vizibil chiar și după ce userul pune o altă întrebare. */
  protected readonly lastResponse = computed<SpendingForecastResponse | null>(() => {
    const messages = this.chatMessages();
    for (let i = messages.length - 1; i >= 0; i--) {
      const response = messages[i].response;
      if (response) return response;
    }
    return null;
  });

  constructor() {
    effect(() => {
      this.chatMessages();
      this.sending();
      const el = this.messagesEl()?.nativeElement;
      if (el) queueMicrotask(() => (el.scrollTop = el.scrollHeight));
    });
  }

  ngOnInit(): void {
    this.loadConversations();
  }

  ngOnDestroy(): void {
    // Nu lăsăm vocea să continue să citească un mesaj după ce userul a
    // plecat de pe pagină (ex. a navigat spre Transferuri în timp ce
    // MaestroAssistent încă citea un răspuns).
    this.speech.stopSpeaking();
  }

  private loadConversations(): void {
    this.copilotApi.listConversations().subscribe({
      next: (list) => this.conversations.set(list),
    });
  }

  protected startNewConversation(): void {
    this.activeConversationId.set(null);
    this.chatMessages.set([]);
  }

  protected openConversation(id: string): void {
    if (id === this.activeConversationId()) return;
    this.copilotApi.getConversation(id).subscribe({
      next: (detail: ConversationDetail) => {
        this.activeConversationId.set(detail.id);
        this.chatMessages.set(
          detail.messages.map((m, index) => ({
            id: index,
            role: m.role,
            text: m.content,
            time: formatChatTime(new Date(m.created_at)),
            response: m.response ?? undefined,
            actionState: m.response?.pending_action ? 'pending' : undefined,
          })),
        );
      },
      error: (err) => this.toast.error(extractErrorMessage(err, 'Nu am putut încărca conversația.')),
    });
  }

  protected deleteConversation(event: Event, id: string): void {
    event.stopPropagation();
    this.copilotApi.deleteConversation(id).subscribe({
      next: () => {
        this.conversations.update((list) => list.filter((c) => c.id !== id));
        if (this.activeConversationId() === id) this.startNewConversation();
      },
      error: (err) => this.toast.error(extractErrorMessage(err, 'Nu am putut șterge conversația.')),
    });
  }

  protected sendMessage(): void {
    const text = this.chatInput().trim();
    if (!text || this.sending()) return;
    this.chatInput.set('');
    this.ask(text);
  }

  /** Microfon — pornește/oprește recunoașterea vocală (ro-RO). Textul
   * recunoscut apare în caseta de input, NU se trimite automat — userul
   * apasă Trimite manual, ca să poată verifica/corecta ce a recunoscut
   * motorul înainte de a pleca mesajul. */
  protected toggleListening(): void {
    if (this.speech.listening()) {
      this.speech.stopListening();
      return;
    }
    this.speech.startListening((text) => {
      if (text) this.chatInput.set(text);
    });
  }

  /** "Ascultă" pe un răspuns — citește cu voce tare textul mesajului (fără
   * sintaxa Markdown-lite brută, vezi stripMarkdownForSpeech). Apăsat din
   * nou pe ACELAȘI mesaj oprește citirea (buton devine "Stop"). */
  protected toggleSpeak(message: ChatMessage): void {
    if (this.speech.speakingMessageId() === message.id) {
      this.speech.stopSpeaking();
      return;
    }
    this.speech.speak(stripMarkdownForSpeech(message.text), message.id);
  }

  /** Întrebare din chip-urile de sugestii (stare goală sau sub input). */
  protected askSuggested(question: string): void {
    if (this.sending()) return;
    this.ask(question);
  }

  private ask(message: string): void {
    this.pushMessage({ id: Date.now(), role: 'user', text: message, time: formatChatTime(new Date()) });
    this.sending.set(true);
    this.sendingSlow.set(false);
    // Majoritatea răspunsurilor vin în 10-20s — dacă trece mai mult,
    // arătăm un indiciu, ca să nu pară că s-a blocat.
    this.slowTimer = setTimeout(() => this.sendingSlow.set(true), 15_000);

    this.copilotApi.sendMessage(message, this.activeConversationId()).subscribe({
      next: (response) => {
        this.stopSending();
        if (!this.activeConversationId()) {
          this.activeConversationId.set(response.conversation_id);
          this.loadConversations();
        }
        this.pushMessage({
          id: Date.now(),
          role: 'assistant',
          text: response.answer,
          time: formatChatTime(new Date()),
          response,
          actionState: response.pending_action ? 'pending' : undefined,
        });
      },
      error: (err) => {
        this.stopSending();
        const errorText = extractErrorMessage(err, 'Nu am putut obține un răspuns acum. Te rugăm să încerci din nou.');
        this.pushMessage({ id: Date.now(), role: 'assistant', text: '', time: formatChatTime(new Date()), errorText });
      },
    });
  }

  private stopSending(): void {
    this.sending.set(false);
    this.sendingSlow.set(false);
    clearTimeout(this.slowTimer);
  }

  private pushMessage(message: ChatMessage): void {
    this.chatMessages.update((messages) => [...messages, message]);
  }

  /** Execută REAL acțiunea propusă (creare/modificare/ștergere buget) —
   * apelată STRICT la click explicit pe "Confirmă". Nu mai trece prin GPT. */
  protected confirmPendingAction(message: ChatMessage): void {
    const action = message.response?.pending_action;
    if (!action || message.actionState !== 'pending') return;

    this.updateActionState(message.id, 'confirming');
    this.copilotApi.confirmAction(action).subscribe({
      next: (result) => {
        this.updateActionState(message.id, result.success ? 'done' : 'error', result.message);
      },
      error: (err) => {
        const errorText = extractErrorMessage(err, 'Nu am putut duce acțiunea la capăt. Încearcă din nou.');
        this.updateActionState(message.id, 'error', errorText);
      },
    });
  }

  protected cancelPendingAction(message: ChatMessage): void {
    if (message.actionState !== 'pending') return;
    this.updateActionState(message.id, 'cancelled');
  }

  private updateActionState(messageId: number, state: PendingActionState, resultText?: string): void {
    this.chatMessages.update((messages) =>
      messages.map((m) => (m.id === messageId ? { ...m, actionState: state, actionResultText: resultText } : m)),
    );
  }

  /** Etichete scurte, prietenoase pentru documentele RAG folosite (ex.
   * "safety_buffer.md" -> "safety buffer") — transparență fără jargon tehnic. */
  protected sourceLabels(sources: { source: string }[]): string {
    return sources.map((s) => s.source.replace(/\.md$/, '').replace(/_/g, ' ')).join(', ');
  }
}
