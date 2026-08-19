import { Component, computed, inject, input, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';

import { AuthService } from '../../../services/auth.service';
import { NotificationsService } from '../notifications/notifications.service';
import { Icon } from '../icon/icon';

/**
 * Bara de sus — search, buton rapid "Tranzacție nouă" (duce la formularul
 * real de transfer, /app/transfers — nu duplicăm logica de transfer aici),
 * notificări, avatar + nume (din backend, NU hardcodat) + tip de cont demo.
 * Vezi UI reference/*.png.
 */
@Component({
  selector: 'app-topbar',
  standalone: true,
  imports: [RouterLink, FormsModule, Icon, DatePipe],
  templateUrl: './topbar.html',
  styleUrl: './topbar.css',
})
export class Topbar {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  protected readonly notificationsService = inject(NotificationsService);

  readonly accountType = input('Client Premium');

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
      this.notificationsService.markAllRead();
    }
  }

  protected toggleProfileMenu(): void {
    this.profileMenuOpen.update((open) => !open);
    this.notificationsOpen.set(false);
  }

  protected logout(): void {
    this.auth.logout();
    this.router.navigate(['/login']);
  }
}
