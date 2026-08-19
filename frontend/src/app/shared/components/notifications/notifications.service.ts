import { Injectable, signal } from '@angular/core';

export interface AppNotification {
  id: number;
  text: string;
  createdAt: Date;
  read: boolean;
}

/**
 * Notificări — versiune MVP, DOAR frontend (in-memory, per sesiune).
 *
 * Task-ul MaestroBank (secțiunea 22) permite explicit ca, dacă un sistem
 * complet de notificări (persistat, backend dedicat) e prea mult pentru
 * această etapă, să pregătim structura fără să blocăm implementarea
 * principală. Acest serviciu se alimentează din aceleași evenimente care
 * declanșează toast-uri (transfer reușit, card blocat, buget aproape
 * atins, tichet de suport creat) — vezi ToastService pentru feedback-ul
 * imediat, acesta e istoricul persistent-în-sesiune, afișat în clopoțel.
 *
 * NU e conectat la un microserviciu — "Coming soon" pentru persistare
 * reală (vezi raportul final).
 */
@Injectable({ providedIn: 'root' })
export class NotificationsService {
  private readonly _notifications = signal<AppNotification[]>([]);
  readonly notifications = this._notifications.asReadonly();
  private nextId = 1;

  get unreadCount(): number {
    return this._notifications().filter((n) => !n.read).length;
  }

  push(text: string): void {
    const notification: AppNotification = { id: this.nextId++, text, createdAt: new Date(), read: false };
    this._notifications.update((list) => [notification, ...list].slice(0, 20));
  }

  markAllRead(): void {
    this._notifications.update((list) => list.map((n) => ({ ...n, read: true })));
  }
}
