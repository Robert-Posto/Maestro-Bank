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
  protected readonly error = signal<string | null>(null);
  protected readonly sessionExpired = this.route.snapshot.queryParamMap.get('sessionExpired') === '1';

  protected readonly passkeySupported = this.webauthn.isSupported();
  protected readonly passkeyBusy = signal(false);

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
        this.router.navigate(['/app/overview']);
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
      this.router.navigate(['/app/overview']);
    } catch (err) {
      this.passkeyBusy.set(false);
      if ((err as { name?: string })?.name === 'NotAllowedError') {
        return; // userul a anulat prompt-ul biometric — nu e o eroare de afișat
      }
      this.error.set(extractErrorMessage(err, 'Autentificarea cu passkey a eșuat. Poți folosi parola.'));
    }
  }
}
