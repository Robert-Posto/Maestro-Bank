import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { API_BASE_URL } from '../core/api-config';

/**
 * Recunoaștere (STT) și sinteză (TTS) vocală pentru MaestroAssistent
 * (features/copilot) și Support Agent (features/support) — aceeași
 * instanță (providedIn: 'root'), ca un singur mesaj să poată fi citit
 * deodată indiferent din ce pagină a pornit.
 *
 * STT: Web Speech API (`SpeechRecognition`/`webkitSpeechRecognition`),
 * 100% client-side — nu are echivalent server-side simplu aici (ar
 * însemna streaming audio către backend). Suport doar Chrome/Edge.
 *
 * TTS: backend (POST /api/ai/speech, vezi ai-orchestrator-service/app/tts.py
 * — `edge-tts`, vocea online gratuită a Microsoft Edge), NU Web Speech API
 * local. Motiv real, descoperit live: `speechSynthesis` depinde de vocile
 * INSTALATE pe mașina userului — pe multe Windows-uri (mai ales cele fără
 * voci suplimentare adăugate) singura voce disponibilă e engleză, deci
 * orice text românesc suna "tradus" (de fapt doar pronunțat greșit).
 * edge-tts nu are nevoie de nimic instalat local — funcționează identic
 * indiferent de sistemul de operare al userului. Web Speech API local
 * rămâne ca FALLBACK silențios dacă backend-ul nu răspunde (offline,
 * ai-orchestrator-service jos etc.) — mai bine o voce posibil greșită
 * decât nicio voce.
 */
interface SpeechRecognitionAlternativeLike {
  transcript: string;
}
interface SpeechRecognitionResultLike {
  readonly length: number;
  [index: number]: SpeechRecognitionAlternativeLike;
}
interface SpeechRecognitionEventLike extends Event {
  readonly results: ArrayLike<SpeechRecognitionResultLike>;
}
interface SpeechRecognitionLike extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start(): void;
  stop(): void;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: Event) => void) | null;
  onend: (() => void) | null;
}
type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

function resolveSpeechRecognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === 'undefined') return null;
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

/**
 * Curăță sintaxa Markdown-lite (vezi shared/pipes/markdown-lite.pipe.ts)
 * ÎNAINTE de a trimite textul la TTS — altfel motorul de voce ar citi
 * literal simbolurile ("steluță steluță cont curent steluță steluță"),
 * nu doar cuvintele. Aceeași sintaxă STRICT limitată ca la pipe-ul de
 * afișare (bold, liste cu marcatori/numerotate) — nu un parser complet.
 */
export function stripMarkdownForSpeech(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .split('\n')
    .map((line) => line.trim().replace(/^[-*]\s+/, '').replace(/^\d+[.)]\s+/, ''))
    .filter(Boolean)
    .join('. ');
}

@Injectable({ providedIn: 'root' })
export class SpeechService {
  private readonly http = inject(HttpClient);
  private readonly recognitionCtor = resolveSpeechRecognitionCtor();
  private recognition: SpeechRecognitionLike | null = null;

  /** Recunoașterea vocală (microfon) — doar Chrome/Edge deocamdată. */
  readonly sttSupported = !!this.recognitionCtor;
  /** Citirea cu voce tare — vezi comentariul din capul fișierului (backend
   * edge-tts, cu fallback pe Web Speech API local dacă backend-ul nu
   * răspunde) — practic mereu true (fallback-ul acoperă chiar și
   * browsere fără speechSynthesis, doar că atunci fallback-ul n-ar avea
   * ce oferi; păstrăm flag-ul pentru claritate, nu schimbă UI-ul azi). */
  readonly ttsSupported = true;

  private cachedLocalVoices: SpeechSynthesisVoice[] = [];
  private localVoicesPromise: Promise<SpeechSynthesisVoice[]> | null = null;

  private loadLocalVoices(): Promise<SpeechSynthesisVoice[]> {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) return Promise.resolve([]);
    if (this.localVoicesPromise) return this.localVoicesPromise;

    this.localVoicesPromise = new Promise((resolve) => {
      const immediate = window.speechSynthesis.getVoices();
      if (immediate.length > 0) {
        resolve(immediate);
        return;
      }
      const onVoicesChanged = () => {
        const voices = window.speechSynthesis.getVoices();
        if (voices.length === 0) return;
        window.speechSynthesis.removeEventListener('voiceschanged', onVoicesChanged);
        clearTimeout(fallbackTimer);
        resolve(voices);
      };
      window.speechSynthesis.addEventListener('voiceschanged', onVoicesChanged);
      const fallbackTimer = setTimeout(() => {
        window.speechSynthesis.removeEventListener('voiceschanged', onVoicesChanged);
        resolve(window.speechSynthesis.getVoices());
      }, 1000);
    });
    return this.localVoicesPromise;
  }

  /** Eristică nume feminin/masculin — vezi comentariul din capul
   * fișierului: Web Speech API nu are un câmp oficial de gen, doar numele
   * vocii (ex. Windows: "Microsoft Ioana" = femeie, "Microsoft Andrei" =
   * bărbat). Folosită DOAR de fallback-ul local (edge-tts, calea
   * principală, are deja o singură voce feminină fixă, aleasă server-side
   * — vezi app/tts.py::_VOICE). */
  private pickLocalRomanianVoice(voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice | null {
    const romanian = voices.filter((v) => v.lang.toLowerCase().startsWith('ro'));
    if (romanian.length === 0) return null;
    if (romanian.length === 1) return romanian[0];

    const femaleHints = ['ioana', 'female', 'femeie', 'woman'];
    const maleHints = ['andrei', 'male', 'bărbat', 'barbat', 'man'];
    const female = romanian.find((v) => femaleHints.some((hint) => v.name.toLowerCase().includes(hint)));
    if (female) return female;

    const notMale = romanian.filter((v) => !maleHints.some((hint) => v.name.toLowerCase().includes(hint)));
    const pool = notMale.length > 0 ? notMale : romanian;
    return pool.find((v) => !v.localService) ?? pool[0];
  }

  readonly listening = signal(false);
  /** id-ul mesajului citit ACUM (sau null) — un singur mesaj citit deodată;
   * un nou "Ascultă" apăsat îl întrerupe automat pe cel anterior (vezi speak). */
  readonly speakingMessageId = signal<number | null>(null);
  private currentAudio: HTMLAudioElement | null = null;
  private currentAudioUrl: string | null = null;

  /**
   * Pornește ascultarea (ro-RO). `onFinalResult` primește textul recunoscut
   * DOAR la finalul vorbirii (nu rezultate parțiale) — populează caseta de
   * input, userul apasă Trimite manual (la cererea userului: nu trimitem
   * automat, ca să poată verifica/corecta înainte).
   */
  startListening(onFinalResult: (text: string) => void, onError?: () => void): void {
    if (!this.recognitionCtor || this.listening()) return;

    const recognition = new this.recognitionCtor();
    recognition.lang = 'ro-RO';
    recognition.continuous = false;
    recognition.interimResults = false;

    recognition.onresult = (event) => {
      const chunks: string[] = [];
      for (let i = 0; i < event.results.length; i++) {
        chunks.push(event.results[i][0].transcript);
      }
      onFinalResult(chunks.join(' ').trim());
    };
    recognition.onerror = () => {
      this.listening.set(false);
      onError?.();
    };
    recognition.onend = () => {
      this.listening.set(false);
    };

    this.recognition = recognition;
    this.listening.set(true);
    recognition.start();
  }

  stopListening(): void {
    this.recognition?.stop();
    this.listening.set(false);
  }

  /** Citește `text` cu voce tare — dacă alt mesaj era deja citit, îl
   * oprește întâi (un singur mesaj deodată, vezi speakingMessageId).
   *
   * Încearcă ÎNTÂI backend-ul (edge-tts — voce română, feminină,
   * indiferent de sistemul de operare al userului, vezi comentariul din
   * capul fișierului). Dacă backend-ul nu răspunde (offline,
   * ai-orchestrator-service jos), cade silențios pe Web Speech API local
   * — degradat, dar tot mai bine decât nimic.
   */
  async speak(text: string, messageId: number): Promise<void> {
    if (!text.trim()) return;
    this.stopSpeaking();
    this.speakingMessageId.set(messageId);

    const audioBlob = await this.fetchBackendSpeech(text);
    // Userul poate fi apăsat "Oprește" (sau a pornit alt mesaj) cât timp
    // așteptam răspunsul backend-ului — nu mai pornim citirea peste noua stare.
    if (this.speakingMessageId() !== messageId) return;

    if (audioBlob) {
      this.playBackendAudio(audioBlob, messageId);
      return;
    }

    await this.speakLocally(text, messageId);
  }

  private async fetchBackendSpeech(text: string): Promise<Blob | null> {
    try {
      return await firstValueFrom(
        this.http.post(`${API_BASE_URL}/ai/speech`, { text }, { responseType: 'blob' }),
      );
    } catch {
      return null;
    }
  }

  private playBackendAudio(blob: Blob, messageId: number): void {
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    this.currentAudio = audio;
    this.currentAudioUrl = url;

    const finish = () => {
      URL.revokeObjectURL(url);
      if (this.currentAudioUrl === url) {
        this.currentAudio = null;
        this.currentAudioUrl = null;
      }
      if (this.speakingMessageId() === messageId) this.speakingMessageId.set(null);
    };
    audio.onended = finish;
    audio.onerror = finish;
    audio.play().catch(finish);
  }

  /** Fallback local — Web Speech API, vezi comentariul din capul
   * fișierului. Rar folosit în practică (doar dacă backend-ul e jos). */
  private async speakLocally(text: string, messageId: number): Promise<void> {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
      if (this.speakingMessageId() === messageId) this.speakingMessageId.set(null);
      return;
    }

    const voices = await this.loadLocalVoices();
    if (this.speakingMessageId() !== messageId) return;

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'ro-RO';
    const voice = this.pickLocalRomanianVoice(voices);
    if (voice) utterance.voice = voice;
    utterance.rate = 0.9;
    utterance.onend = () => {
      if (this.speakingMessageId() === messageId) this.speakingMessageId.set(null);
    };
    utterance.onerror = () => {
      if (this.speakingMessageId() === messageId) this.speakingMessageId.set(null);
    };

    window.speechSynthesis.speak(utterance);
  }

  /** Oprește citirea în curs (dacă vreuna, backend SAU local) — apelată și
   * la navigare între pagini (vezi ngOnDestroy în Copilot/Support), ca
   * vocea să nu continue să citească un mesaj după ce userul a plecat de
   * pe pagină. */
  stopSpeaking(): void {
    if (this.currentAudio) {
      this.currentAudio.pause();
      if (this.currentAudioUrl) URL.revokeObjectURL(this.currentAudioUrl);
      this.currentAudio = null;
      this.currentAudioUrl = null;
    }
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
    this.speakingMessageId.set(null);
  }
}
