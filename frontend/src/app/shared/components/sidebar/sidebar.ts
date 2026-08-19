import { Component, output } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

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
  { label: 'MaestroAssistent', route: '/app/copilot', icon: 'copilot' },
  { label: 'Profil & Securitate', route: '/app/profile', icon: 'profile' },
];

/** Sidebar bleumarin — vezi UI reference/*.png. Comun tuturor paginilor /app/*. */
@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [RouterLink, RouterLinkActive, Icon],
  templateUrl: './sidebar.html',
  styleUrl: './sidebar.css',
})
export class Sidebar {
  protected readonly navItems = NAV_ITEMS;
  readonly logoutRequested = output<void>();
}
