import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';

import { API_BASE_URL } from '../../../core/api-config';

export type NotificationKind =
  | 'budget'
  | 'card'
  | 'transfer'
  | 'transfer_received'
  | 'transfer_hold'
  | 'transfer_hold_cancelled'
  | 'system'
  | 'document_sign';

export interface AppNotification {
  id: string;
  kind: NotificationKind;
  text: string;
  read: boolean;
  createdAt: Date;
  /** Id-ul resursei la care se referă (ex. id-ul tranzacției) — absent pe
   * notificările create înainte de acest câmp, sau pe tipuri fără o
   * resursă anume (ex. "system"). Vezi Topbar::openNotification. */
  referenceId?: string;
}

interface NotificationApiView {
  id: string;
  kind: NotificationKind;
  text: string;
  read: boolean;
  created_at: string;
  reference_id?: string | null;
}

/**
 * Notificări — istoric PERSISTENT, alimentat de backend (support-service).
 *
 * Evenimente reale care creează o notificare acum: transfer reușit
 * (transactions-service), card blocat (accounts-service) — vezi
 * app/service.py::_notify_user în fiecare. Alte servicii pot adăuga
 * propriile evenimente apelând POST /internal/notifications, fără nicio
 * schimbare aici.
 *
 * Polling simplu (nu WebSocket/SSE — overkill pentru un demo), pornit din
 * Topbar (singurul loc unde clopoțelul e afișat) cât timp userul e
 * autentificat.
 */
@Injectable({ providedIn: 'root' })
export class NotificationsService {
  private readonly http = inject(HttpClient);
  private readonly _notifications = signal<AppNotification[]>([]);
  readonly notifications = this._notifications.asReadonly();

  get unreadCount(): number {
    return this._notifications().filter((n) => !n.read).length;
  }

  refresh(): void {
    this.http.get<NotificationApiView[]>(`${API_BASE_URL}/support/notifications`).subscribe({
      next: (list) => this._notifications.set(list.map(toAppNotification)),
      error: () => {
        // Eșec silențios — notificările nu sunt critice, nu merită un toast
        // care întrerupe userul la fiecare 30s dacă backend-ul are o problemă.
      },
    });
  }

  markAllRead(): void {
    if (this.unreadCount === 0) return;
    this.http.patch<void>(`${API_BASE_URL}/support/notifications/read-all`, {}).subscribe({
      next: () => this._notifications.update((list) => list.map((n) => ({ ...n, read: true }))),
      error: () => {},
    });
  }

  /**
   * Șterge o notificare. Dispare din listă IMEDIAT, înainte de răspunsul
   * serverului — e o acțiune mică și previzibilă, iar o pauză de câteva
   * sute de milisecunde între click și dispariție ar face butonul să pară
   * stricat. Dacă apelul chiar eșuează, o punem înapoi.
   */
  remove(id: string): void {
    const previous = this._notifications();
    this._notifications.set(previous.filter((n) => n.id !== id));

    this.http.delete<void>(`${API_BASE_URL}/support/notifications/${id}`).subscribe({
      error: () => this._notifications.set(previous),
    });
  }
}

function toAppNotification(view: NotificationApiView): AppNotification {
  return {
    id: view.id,
    kind: view.kind,
    text: view.text,
    read: view.read,
    createdAt: new Date(view.created_at),
    referenceId: view.reference_id ?? undefined,
  };
}
