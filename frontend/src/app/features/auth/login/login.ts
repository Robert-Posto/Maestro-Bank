import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { AuthService } from '../../../services/auth.service';
import { extractErrorMessage } from '../../../shared/error-utils';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [FormsModule, RouterLink],
  templateUrl: './login.html',
  styleUrl: './login.css',
})
export class Login {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  protected readonly email = signal('');
  protected readonly password = signal('');
  protected readonly isSubmitting = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly sessionExpired = this.route.snapshot.queryParamMap.get('sessionExpired') === '1';

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
}
