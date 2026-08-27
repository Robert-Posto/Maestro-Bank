import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { AuthService } from '../../../services/auth.service';
import { WebauthnService } from '../../../services/webauthn.service';
import { Icon } from '../../../shared/components/icon/icon';
import { extractErrorMessage } from '../../../shared/error-utils';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [FormsModule, RouterLink, Icon],
  templateUrl: './login.html',
  styleUrl: './login.css',
})
export class Login {
  private readonly auth = inject(AuthService);
  private readonly webauthn = inject(WebauthnService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  protected readonly email = signal('');
  protected readonly password = signal('');
  protected readonly isSubmitting = signal(false);
  /** Parola vizibilă în clar — pornește mereu ascunsă la fiecare intrare pe
   * ecran; nu reținem preferința nicăieri, ca o parolă să nu ajungă vizibilă
   * din start pe un ecran pe care se poate uita altcineva. */
  protected readonly passwordVisible = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly sessionExpired = this.route.snapshot.queryParamMap.get('sessionExpired') === '1';

  /** Unde ajunge userul DUPĂ login — implicit /app/overview, dar dacă a
   * fost trimis aici de authGuard (ex. a deschis un link de "Cerere de
   * plată" neautentificat, vezi auth.guard.ts), îl ducem înapoi EXACT unde
   * voia să ajungă, nu pe overview. Validăm că e o rută internă `/app/*`
   * — niciodată un URL extern (open-redirect) — `returnUrl` vine dintr-un
   * query param, deci e tehnic controlabil de oricine construiește linkul. */
  private readonly returnUrl = this.resolveReturnUrl();

  private resolveReturnUrl(): string {
    const raw = this.route.snapshot.queryParamMap.get('returnUrl');
    return raw && raw.startsWith('/app/') ? raw : '/app/overview';
  }

  protected readonly passkeySupported = this.webauthn.isSupported();
  protected readonly passkeyBusy = signal(false);

  protected togglePasswordVisibility(): void {
    this.passwordVisible.update((visible) => !visible);
  }

  submit(): void {
    this.error.set(null);
    if (!this.email().trim() || !this.password()) {
      this.error.set('Completează email-ul și parola.');
      return;
    }

    this.isSubmitting.set(true);
    this.auth.login({ email: this.email().trim(), password: this.password() }).subscribe({
      next: () => {
        this.isSubmitting.set(false);
        this.router.navigateByUrl(this.returnUrl);
      },
      error: (err) => {
        this.isSubmitting.set(false);
        this.error.set(extractErrorMessage(err, 'Autentificare eșuată. Verifică email-ul și parola.'));
      },
    });
  }

  protected async loginWithPasskey(): Promise<void> {
    this.error.set(null);
    if (!this.email().trim()) {
      this.error.set('Completează email-ul, apoi folosește passkey-ul.');
      return;
    }

    this.passkeyBusy.set(true);
    try {
      await this.webauthn.loginWithPasskey(this.email().trim());
      this.passkeyBusy.set(false);
      this.router.navigateByUrl(this.returnUrl);
    } catch (err) {
      this.passkeyBusy.set(false);
      if ((err as { name?: string })?.name === 'NotAllowedError') {
        return; // userul a anulat prompt-ul biometric — nu e o eroare de afișat
      }
      this.error.set(extractErrorMessage(err, 'Autentificarea cu passkey a eșuat. Poți folosi parola.'));
    }
  }
}
