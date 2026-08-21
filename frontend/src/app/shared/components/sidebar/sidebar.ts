import { Component, computed, inject } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

import { AuthService } from '../../../services/auth.service';
import { Icon } from '../icon/icon';

interface NavItem {
  label: string;
  route: string;
  icon: string;
}

const NAV_ITEMS: NavItem[] = [
  { label: 'Overview', route: '/app/overview', icon: 'overview' },
  { label: 'Conturi', route: '/app/accounts', icon: 'accounts' },
  { label: 'Carduri', route: '/app/cards', icon: 'cards' },
  { label: 'Tranzacții', route: '/app/transactions', icon: 'transactions' },
  { label: 'Plăți & Transferuri', route: '/app/transfers', icon: 'transfer' },
  { label: 'Schimb valutar', route: '/app/exchange', icon: 'exchange' },
  { label: 'Bugete', route: '/app/budgets', icon: 'budgets' },
  { label: 'Spending & Forecast', route: '/app/spending-forecast', icon: 'spending' },
  { label: 'Support', route: '/app/support', icon: 'support' },
  // Profil & Securitate și Ieși din cont NU sunt aici — trăiesc doar în
  // dropdown-ul de profil din topbar, ca sidebar-ul să nu fie aglomerat
  // cu ceva ce ține de cont, nu de navigare între secțiuni.
  // MaestroAssistent NU e aici — link-ul lui trăiește doar în promo-ul din
  // footer (mai jos), ca să nu apară de 2 ori în același sidebar pentru o
  // funcționalitate care oricum e doar placeholder ("Coming soon").
];

const STAFF_NAV_ITEM: NavItem = { label: 'Personal — Rețineri', route: '/app/staff-holds', icon: 'shield' };

/** Sidebar bleumarin — vezi UI reference/*.png. Comun tuturor paginilor /app/*. */
@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [RouterLink, RouterLinkActive, Icon],
  templateUrl: './sidebar.html',
  styleUrl: './sidebar.css',
})
export class Sidebar {
  private readonly auth = inject(AuthService);

  // currentUser e populat de AppShell la intrarea în /app/* (vezi
  // app-shell.ts) — până se rezolvă, role e undefined și intrarea de
  // personal rămâne ascunsă (fail-safe: mai bine ascunsă o clipă în plus
  // decât arătată cuiva care nu e staff). Server-side, require_staff tot
  // ar bloca oricum orice apel real — asta e DOAR un indiciu de UI.
  protected readonly navItems = computed<NavItem[]>(() => {
    const isStaff = this.auth.currentUser()?.role === 'staff';
    return isStaff ? [...NAV_ITEMS, STAFF_NAV_ITEM] : NAV_ITEMS;
  });
}
