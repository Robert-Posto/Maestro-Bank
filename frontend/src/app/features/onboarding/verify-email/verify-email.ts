import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { AuthService } from '../../../services/auth.service';
import { extractErrorMessage } from '../../../shared/error-utils';
import { Icon } from '../../../shared/components/icon/icon';

/** Pasul 1/3 din onboarding — cod de 6 cifre trimis pe email la register. */
@Component({
  selector: 'app-verify-email',
  standalone: true,
  imports: [FormsModule, Icon],
  templateUrl: './verify-email.html',
  styleUrl: './verify-email.css',
})
export class VerifyEmail {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  protected readonly email = this.auth.currentUser()?.email ?? '';
  protected readonly code = signal('');
  protected readonly isSubmitting = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly resent = signal(false);
  protected readonly resending = signal(false);

  submit(): void {
    this.error.set(null);
    this.resent.set(false);

    const code = this.code().trim();
    if (code.length !== 6) {
      this.error.set('Codul are 6 cifre.');
      return;
    }

    this.isSubmitting.set(true);
    this.auth.verifyEmail(code).subscribe({
      next: () => {
        // Reîmprospătăm signal-ul cu email_verified=true ÎNAINTE de a
        // naviga — altfel guard-ul pasului următor vede încă valoarea
        // veche (cache-uită în currentUser) și ne-ar trimite înapoi aici.
        this.auth.fetchCurrentUser().subscribe({
          next: () => {
            this.isSubmitting.set(false);
            this.router.navigate(['/onboarding/verify-identity']);
          },
          error: () => {
            this.isSubmitting.set(false);
            this.router.navigate(['/onboarding/verify-identity']);
          },
        });
      },
      error: (err) => {
        this.isSubmitting.set(false);
        this.error.set(extractErrorMessage(err, 'Cod incorect. Încearcă din nou.'));
      },
    });
  }

  /** Nu există un "pas anterior" real odată ce contul e creat — "back"
   * aici înseamnă abandonarea onboarding-ului, nu revenirea la register
   * (care oricum ar respinge emailul ca fiind deja folosit). */
  back(): void {
    this.auth.logout();
    this.router.navigate(['/login']);
  }

  resendCode(): void {
    this.error.set(null);
    this.resent.set(false);
    this.resending.set(true);
    this.auth.resendVerificationEmail().subscribe({
      next: () => {
        this.resending.set(false);
        this.resent.set(true);
      },
      error: (err) => {
        this.resending.set(false);
        this.error.set(extractErrorMessage(err, 'Nu am putut retrimite codul.'));
      },
    });
  }
}
