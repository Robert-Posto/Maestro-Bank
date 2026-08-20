import { Component, OnDestroy, OnInit, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';

import { AuthService } from '../../../services/auth.service';
import { IdleService } from '../../../services/idle.service';
import { Sidebar } from '../sidebar/sidebar';
import { Topbar } from '../topbar/topbar';
import { ToastContainer } from '../toast/toast-container';

/**
 * Shell comun tuturor paginilor /app/* — sidebar + topbar + conținut.
 *
 * Încarcă userul curent AICI (o singură dată, la intrarea în secțiunea
 * /app/*), nu în fiecare pagină individuală — altfel un refresh direct
 * pe orice rută în afară de Overview/Cards ar lăsa topbar-ul fără nume
 * (vezi task-ul MaestroBank, secțiunea 34: "refresh pe Angular route
 * trebuie să funcționeze").
 */
@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [RouterOutlet, Sidebar, Topbar, ToastContainer],
  templateUrl: './app-shell.html',
  styleUrl: './app-shell.css',
})
export class AppShell implements OnInit, OnDestroy {
  private readonly auth = inject(AuthService);
  private readonly idle = inject(IdleService);

  ngOnInit(): void {
    if (!this.auth.currentUser()) {
      this.auth.fetchCurrentUser().subscribe();
    }
    // Deconectare automată la inactivitate — DOAR cât timp userul e efectiv
    // în /app/*, nu pe login/register/onboarding (vezi IdleService).
    this.idle.start();
  }

  ngOnDestroy(): void {
    this.idle.stop();
  }
}
