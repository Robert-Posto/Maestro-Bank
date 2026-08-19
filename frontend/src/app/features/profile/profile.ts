import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';
import { Router } from '@angular/router';

import { AuthService } from '../../services/auth.service';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { ActionButton } from '../../shared/components/action-button/action-button';
import { decodeJwtPayload } from '../../shared/jwt-utils';
import { ToastService } from '../../shared/components/toast/toast.service';
import { extractErrorMessage } from '../../shared/error-utils';

/** Profil & Securitate — vezi task-ul MaestroBank, secțiunea 21. */
@Component({
  selector: 'app-profile',
  standalone: true,
  imports: [FormsModule, DatePipe, PageHeader, ActionButton],
  templateUrl: './profile.html',
  styleUrl: './profile.css',
})
export class Profile implements OnInit {
  private readonly auth = inject(AuthService);
  private readonly toast = inject(ToastService);
  private readonly router = inject(Router);

  protected readonly currentUser = this.auth.currentUser;

  protected readonly currentPassword = signal('');
  protected readonly newPassword = signal('');
  protected readonly confirmPassword = signal('');
  protected readonly changingPassword = signal(false);
  protected readonly passwordError = signal<string | null>(null);
  protected readonly passwordSuccess = signal(false);

  protected readonly sessionExpiry = computed(() => {
    const token = this.auth.getToken();
    if (!token) return null;
    const payload = decodeJwtPayload(token);
    if (!payload?.exp) return null;
    return new Date(payload.exp * 1000);
  });

  ngOnInit(): void {
    // Userul curent e deja încărcat de AppShell (o singură dată, la
    // intrarea în secțiunea /app/*) — nu-l reîncărcăm aici.
  }

  protected changePassword(): void {
    this.passwordError.set(null);
    this.passwordSuccess.set(false);

    if (!this.currentPassword() || !this.newPassword() || !this.confirmPassword()) {
      this.passwordError.set('Completează toate câmpurile.');
      return;
    }
    if (this.newPassword() !== this.confirmPassword()) {
      this.passwordError.set('Parola nouă și confirmarea nu coincid.');
      return;
    }

    this.changingPassword.set(true);
    this.auth.changePassword({ current_password: this.currentPassword(), new_password: this.newPassword() }).subscribe({
      next: () => {
        this.changingPassword.set(false);
        this.passwordSuccess.set(true);
        this.currentPassword.set('');
        this.newPassword.set('');
        this.confirmPassword.set('');
        this.toast.success('Parola a fost schimbată cu succes.');
      },
      error: (err) => {
        this.changingPassword.set(false);
        this.passwordError.set(extractErrorMessage(err, 'Schimbarea parolei a eșuat.'));
      },
    });
  }

  protected logout(): void {
    this.auth.logout();
    this.router.navigate(['/login']);
  }
}
