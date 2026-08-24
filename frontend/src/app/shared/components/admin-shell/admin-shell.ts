import { Component, OnDestroy, OnInit, inject } from '@angular/core';
import { Router, RouterOutlet } from '@angular/router';

import { AuthService } from '../../../services/auth.service';
import { IdleService } from '../../../services/idle.service';
import { Icon } from '../icon/icon';
import { ToastContainer } from '../toast/toast-container';

/**
 * Shell DEDICAT zonei de personal (/admin/*) — deliberat separat de
 * AppShell (customer), nu doar o pagină ascunsă în sidebar-ul obișnuit.
 * Contul de personal e emis direct de bancă (vezi scripts/create_staff_user.py),
 * NU e un client cu cont propriu — n-are un "/app/*" al lui de întors, deci
 * acest shell e SINGURA destinație posibilă pentru role="staff" (authGuard
 * îl redirecționează aici dacă ar încerca /app/* direct din URL).
 */
@Component({
  selector: 'app-admin-shell',
  standalone: true,
  imports: [RouterOutlet, Icon, ToastContainer],
  templateUrl: './admin-shell.html',
  styleUrl: './admin-shell.css',
})
export class AdminShell implements OnInit, OnDestroy {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly idle = inject(IdleService);

  protected readonly staffName = this.auth.currentUser()?.first_name ?? 'Personal';

  ngOnInit(): void {
    // Aceleași reguli de deconectare la inactivitate ca /app/* — cu date
    // de fraudă/clienți pe ecran, o consolă de personal uitată deschisă
    // merită cel puțin la fel de multă grijă cât un cont obișnuit.
    this.idle.start();
  }

  ngOnDestroy(): void {
    this.idle.stop();
  }

  protected logout(): void {
    this.auth.logout();
    this.router.navigate(['/login']);
  }
}
