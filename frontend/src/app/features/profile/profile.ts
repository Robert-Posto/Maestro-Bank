import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';
import { Router } from '@angular/router';

import { AuthService } from '../../services/auth.service';
import { PasskeyCredential, WebauthnService } from '../../services/webauthn.service';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { ActionButton } from '../../shared/components/action-button/action-button';
import { ConfirmDialog } from '../../shared/components/confirm-dialog/confirm-dialog';
import { Icon } from '../../shared/components/icon/icon';
import { decodeJwtPayload } from '../../shared/jwt-utils';
import { ToastService } from '../../shared/components/toast/toast.service';
import { extractErrorMessage } from '../../shared/error-utils';

/** Profil & Securitate — vezi task-ul MaestroBank, secțiunea 21. */
@Component({
  selector: 'app-profile',
  standalone: true,
  imports: [FormsModule, DatePipe, PageHeader, ActionButton, ConfirmDialog, Icon],
  templateUrl: './profile.html',
  styleUrl: './profile.css',
})
export class Profile implements OnInit {
  private readonly auth = inject(AuthService);
  private readonly webauthn = inject(WebauthnService);
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

  protected readonly passkeySupported = this.webauthn.isSupported();
  protected readonly passkeysLoading = signal(true);
  protected readonly passkeys = signal<PasskeyCredential[]>([]);
  protected readonly enrollingPasskey = signal(false);
  protected readonly pendingRevoke = signal<PasskeyCredential | null>(null);
  protected readonly revokingPasskey = signal(false);

  ngOnInit(): void {
    // Userul curent e deja încărcat de AppShell (o singură dată, la
    // intrarea în secțiunea /app/*) — nu-l reîncărcăm aici.
    if (this.passkeySupported) {
      this.loadPasskeys();
    } else {
      this.passkeysLoading.set(false);
    }
  }

  private loadPasskeys(): void {
    this.passkeysLoading.set(true);
    this.webauthn.listCredentials().subscribe({
      next: (credentials) => {
        this.passkeys.set(credentials);
        this.passkeysLoading.set(false);
      },
      error: () => this.passkeysLoading.set(false),
    });
  }

  protected async addPasskey(): Promise<void> {
    this.enrollingPasskey.set(true);
    try {
      await this.webauthn.registerPasskey();
      this.toast.success('Passkey adăugat.');
      this.loadPasskeys();
    } catch (err) {
      if ((err as { name?: string })?.name !== 'NotAllowedError') {
        this.toast.error(extractErrorMessage(err, 'Nu am putut adăuga passkey-ul.'));
      }
    } finally {
      this.enrollingPasskey.set(false);
    }
  }

  protected confirmRevokePasskey(): void {
    const target = this.pendingRevoke();
    if (!target) return;

    this.revokingPasskey.set(true);
    this.webauthn.revokeCredential(target.id).subscribe({
      next: () => {
        this.passkeys.update((list) => list.filter((p) => p.id !== target.id));
        this.revokingPasskey.set(false);
        this.pendingRevoke.set(null);
        this.toast.success('Passkey revocat.');
      },
      error: (err) => {
        this.revokingPasskey.set(false);
        this.toast.error(extractErrorMessage(err, 'Nu am putut revoca passkey-ul.'));
      },
    });
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
