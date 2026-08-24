import { Component, computed, inject } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

import { AuthService } from '../../../services/auth.service';
import { Icon } from '../icon/icon';

interface NavItem {
  label: string;
  route: string;
  icon: string;
  /** Insignă mică opțională lângă etichetă (ex. "AI") — vezi sidebar.css::sidebar__link-badge. */
  badge?: string;
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
  // MaestroAgent (fost "MaestroAssistent") — funcțional acum (agentul
  // Spending + Forecast, peste GPT-5-mini), deci e o intrare normală de
  // navigare, ca oricare alta — NU mai e un card promo separat în footer.
  { label: 'MaestroAgent', route: '/app/copilot', icon: 'copilot', badge: 'AI' },
  { label: 'Support', route: '/app/support', icon: 'support' },
  // Profil & Securitate și Ieși din cont NU sunt aici — trăiesc doar în
  // dropdown-ul de profil din topbar, ca sidebar-ul să nu fie aglomerat
  // cu ceva ce ține de cont, nu de navigare între secțiuni.
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
