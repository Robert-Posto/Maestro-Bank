import { Component, ElementRef, HostListener, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';

import { AuthService } from '../../../services/auth.service';
import { ThemeService } from '../../../services/theme.service';
import { AppNotification, NotificationKind, NotificationsService } from '../notifications/notifications.service';
import { Icon } from '../icon/icon';

/** Unde duce click-ul pe o notificare, după tipul ei — vezi
 * NotificationKind (support-service/app/models.py e sursa reală a
 * valorilor). Nu avem un id de resursă atașat notificării (doar `kind` +
 * `text`), deci mapăm pe pagina relevantă tipului, nu pe o resursă exactă. */
const NOTIFICATION_ROUTES: Record<NotificationKind, string[]> = {
  budget: ['/app/budgets'],
  card: ['/app/cards'],
  transfer: ['/app/transactions'],
  transfer_received: ['/app/transactions'],
  transfer_hold: ['/app/transactions'],
  transfer_hold_cancelled: ['/app/transactions'],
  system: ['/app/overview'],
  document_sign: ['/app/profile'],
};

/** Tipuri care au un `referenceId` = id de tranzacție (vezi
 * transactions-service::_notify_user) — la click, deschidem direct
 * descrierea acelei tranzacții (vezi Transactions::ngOnInit,
 * query param `highlight`), nu doar lista generică. */
const TRANSACTION_NOTIFICATION_KINDS = new Set<NotificationKind>([
  'transfer',
  'transfer_received',
  'transfer_hold',
  'transfer_hold_cancelled',
]);

/**
 * Bara de sus — search, buton rapid "Tranzacție nouă" (duce la formularul
 * real de transfer, /app/transfers — nu duplicăm logica de transfer aici),
 * notificări, avatar + nume (din backend, NU hardcodat).
 * Vezi UI reference/*.png.
 */
const NOTIFICATIONS_POLL_INTERVAL_MS = 30_000;

@Component({
  selector: 'app-topbar',
  standalone: true,
  imports: [RouterLink, FormsModule, Icon, DatePipe],
  templateUrl: './topbar.html',
  styleUrl: './topbar.css',
})
export class Topbar implements OnInit, OnDestroy {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly elementRef = inject(ElementRef<HTMLElement>);
  protected readonly notificationsService = inject(NotificationsService);
  protected readonly themeService = inject(ThemeService);

  protected readonly currentUser = this.auth.currentUser;
  protected readonly fullName = computed(() => {
    const user = this.currentUser();
    return user ? `${user.first_name} ${user.last_name}` : '';
  });
  protected readonly initials = computed(() => {
    const user = this.currentUser();
    if (!user) return '';
    return `${user.first_name.charAt(0)}${user.last_name.charAt(0)}`.toUpperCase();
  });

  protected readonly searchTerm = signal('');
  protected readonly notificationsOpen = signal(false);
  protected readonly profileMenuOpen = signal(false);
  protected readonly notifications = this.notificationsService.notifications;

  private pollHandle: ReturnType<typeof setInterval> | undefined;

  ngOnInit(): void {
    this.notificationsService.refresh();
    this.pollHandle = setInterval(() => this.notificationsService.refresh(), NOTIFICATIONS_POLL_INTERVAL_MS);
  }

  ngOnDestroy(): void {
    clearInterval(this.pollHandle);
  }

  protected onSearch(): void {
    const term = this.searchTerm().trim();
    this.router.navigate(['/app/transactions'], term ? { queryParams: { search: term } } : {});
  }

  protected newTransaction(): void {
    this.notificationsOpen.set(false);
    this.profileMenuOpen.set(false);
    this.router.navigate(['/app/transfers']);
  }

  protected toggleNotifications(): void {
    this.notificationsOpen.update((open) => !open);
    this.profileMenuOpen.set(false);
    if (this.notificationsOpen()) {
      this.notificationsService.refresh();
      this.notificationsService.markAllRead();
    }
  }

  protected removeNotification(notification: AppNotification, event: Event): void {
    // Butonul stă în interiorul rândului — fără asta, click-ul ar închide
    // și dropdown-ul (vezi listener-ul de click din afara componentei).
    event.stopPropagation();
    this.notificationsService.remove(notification.id);
  }

  protected openNotification(notification: AppNotification): void {
    this.notificationsOpen.set(false);
    // Dispare din listă imediat ce a servit scopul (te-a dus unde trebuie)
    // — o notificare citită și folosită nu are motiv să mai rămână acolo.
    this.notificationsService.remove(notification.id);

    const commands = NOTIFICATION_ROUTES[notification.kind];
    if (notification.kind === 'document_sign') {
      // Fragment, nu query param — pagina de Profil e cu totul o singură
      // pagină derulabilă (fără taburi), deci "navigarea corectă" aici
      // înseamnă și scroll direct la secțiunea relevantă, nu doar pagina.
      this.router.navigate(commands, { fragment: 'documente-de-semnat' });
      return;
    }
    if (TRANSACTION_NOTIFICATION_KINDS.has(notification.kind) && notification.referenceId) {
      this.router.navigate(commands, { queryParams: { highlight: notification.referenceId } });
      return;
    }
    this.router.navigate(commands);
  }

  protected toggleProfileMenu(): void {
    this.profileMenuOpen.update((open) => !open);
    this.notificationsOpen.set(false);
  }

  protected logout(): void {
    this.auth.logout();
    this.router.navigate(['/login']);
  }

  @HostListener('document:click', ['$event'])
  protected onDocumentClick(event: MouseEvent): void {
    if (!this.notificationsOpen() && !this.profileMenuOpen()) return;
    if (!this.elementRef.nativeElement.contains(event.target as Node)) {
      this.notificationsOpen.set(false);
      this.profileMenuOpen.set(false);
    }
  }
}
