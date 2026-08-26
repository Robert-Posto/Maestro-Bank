import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

import { Icon } from '../icon/icon';

interface NavItem {
  label: string;
  route: string;
  icon: string;
  /** Insignă mică opțională lângă etichetă (ex. "AI") — vezi sidebar.css::sidebar__link-badge. */
  badge?: string;
  /** Tratament vizual distinct (gradient discret) — pentru intrarea AI, ca
   * să nu se piardă în lista de navigare utilitară. Vezi sidebar__link--accent. */
  accent?: boolean;
}

interface NavGroup {
  /** Etichetă mică, opțională, deasupra grupului (ex. "BANCAR") — omisă
   * pentru primul și ultimul grup, ca să nu pară "etichetate" inutil. */
  label?: string;
  items: NavItem[];
}

// Grupate logic (nu o listă plată de 9 linkuri) — Overview e singur, sus,
// ca punct de intrare; restul grupate pe scop, nu pe ordinea în care au
// fost adăugate funcționalitățile.
const NAV_GROUPS: NavGroup[] = [
  {
    items: [{ label: 'Overview', route: '/app/overview', icon: 'overview' }],
  },
  {
    label: 'Bancar',
    items: [
      { label: 'Conturi', route: '/app/accounts', icon: 'accounts' },
      { label: 'Carduri', route: '/app/cards', icon: 'cards' },
      { label: 'Tranzacții', route: '/app/transactions', icon: 'transactions' },
      { label: 'Plăți & Transferuri', route: '/app/transfers', icon: 'transfer' },
      { label: 'Schimb valutar', route: '/app/exchange', icon: 'exchange' },
    ],
  },
  {
    label: 'Planificare',
    items: [
      { label: 'Bugete', route: '/app/budgets', icon: 'budgets' },
      { label: 'Spending & Forecast', route: '/app/spending-forecast', icon: 'spending' },
    ],
  },
  {
    // Etichetat, ca "Bancar"/"Planificare" mai sus — fără label, grupul
    // ăsta ieșea în evidență ca "orfan" față de restul, inconsecvent
    // vizual, deși cele două intrări sunt deja rudă (ambele agenți AI
    // găzduiți de ai-orchestrator-service).
    label: 'Asistenți AI',
    items: [
      // MaestroAgent (fost "MaestroAssistent") — funcțional acum (agentul
      // Spending + Forecast, peste GPT-5-mini), deci e o intrare normală
      // de navigare, ca oricare alta — NU mai e un card promo în footer.
      { label: 'MaestroAgent', route: '/app/copilot', icon: 'copilot', badge: 'AI', accent: true },
      { label: 'Support', route: '/app/support', icon: 'support' },
    ],
  },
  // Profil & Securitate și Ieși din cont NU sunt aici — trăiesc doar în
  // dropdown-ul de profil din topbar, ca sidebar-ul să nu fie aglomerat
  // cu ceva ce ține de cont, nu de navigare între secțiuni.
  //
  // Zona de personal (rețineri fraud) NU e aici — trăiește separat, sub
  // /admin (vezi AdminShell + app.routes.ts), nu ca o intrare în plus în
  // navigarea obișnuită a unui cont de client.
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
  protected readonly navGroups = NAV_GROUPS;
}
