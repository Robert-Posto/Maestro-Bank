import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { AuthService } from '../../../services/auth.service';
import { extractErrorMessage } from '../../../shared/error-utils';
import { Icon } from '../../../shared/components/icon/icon';

@Component({
  selector: 'app-register',
  standalone: true,
  imports: [FormsModule, RouterLink, Icon],
  templateUrl: './register.html',
  styleUrl: './register.css',
})
export class Register {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  protected readonly firstName = signal('');
  protected readonly lastName = signal('');
  protected readonly email = signal('');
  protected readonly phoneNumber = signal('');
  protected readonly password = signal('');
  /** Vezi login.ts — pornește mereu ascunsă, preferința nu se reține. */
  protected readonly passwordVisible = signal(false);
  protected readonly isSubmitting = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly success = signal(false);

  protected togglePasswordVisibility(): void {
    this.passwordVisible.update((visible) => !visible);
  }

  submit(): void {
    this.error.set(null);

    if (!this.firstName().trim() || !this.lastName().trim() || !this.email().trim() || !this.phoneNumber().trim() || !this.password()) {
      this.error.set('Completează toate câmpurile.');
      return;
    }

    this.isSubmitting.set(true);
    this.auth
      .register({
        first_name: this.firstName().trim(),
        last_name: this.lastName().trim(),
        email: this.email().trim(),
        phone_number: this.phoneNumber().trim(),
        password: this.password(),
      })
      .subscribe({
        next: () => {
          this.success.set(true);
          this.isSubmitting.set(false);
          this.auth.login({ email: this.email().trim(), password: this.password() }).subscribe({
            next: () => this.router.navigate(['/app/overview']),
            error: () => this.router.navigate(['/login']),
          });
        },
        error: (err) => {
          this.isSubmitting.set(false);
          this.error.set(extractErrorMessage(err, 'Înregistrarea a eșuat.'));
        },
      });
  }
}
