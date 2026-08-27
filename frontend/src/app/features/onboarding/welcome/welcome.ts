import { Component, OnInit, inject, signal } from '@angular/core';
import { Router } from '@angular/router';

import { AccountView, BankingService } from '../../../services/banking.service';
import { AuthService } from '../../../services/auth.service';
import { AuthLanguageToggle } from '../../../shared/components/auth-language-toggle/auth-language-toggle';
import { Icon } from '../../../shared/components/icon/icon';
import { MoneyPipe } from '../../../shared/pipes/money.pipe';
import { TranslatePipe } from '../../../shared/pipes/translate.pipe';

const WELCOME_BONUS_MINOR = 50_000; // 500 lei — vezi accounts-service POST /accounts/dev/fund

/** Pasul 3/3 din onboarding — cont verificat, bonus de bun venit acordat
 * automat (reutilizează dev/fund, deja existent — vezi banking.service.ts),
 * ca userul să aibă ceva de explorat (transfer, card) din prima secundă. */
@Component({
  selector: 'app-welcome',
  standalone: true,
  imports: [Icon, MoneyPipe, TranslatePipe, AuthLanguageToggle],
  templateUrl: './welcome.html',
  styleUrl: './welcome.css',
})
export class Welcome implements OnInit {
  private readonly banking = inject(BankingService);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  protected readonly firstName = this.auth.currentUser()?.first_name ?? '';
  protected readonly bonusAmountMinor = WELCOME_BONUS_MINOR;
  protected readonly loading = signal(true);
  protected readonly account = signal<AccountView | null>(null);

  ngOnInit(): void {
    this.banking.devFund(WELCOME_BONUS_MINOR).subscribe({
      next: (account) => {
        this.account.set(account);
        this.loading.set(false);
      },
      // Dacă bonusul eșuează (ex. accounts-service jos), tot lăsăm userul
      // să intre în aplicație — nu blocăm onboarding-ul pentru un bonus demo.
      error: () => this.loading.set(false),
    });
  }

  protected enterApp(): void {
    this.router.navigate(['/app/overview']);
  }
}
