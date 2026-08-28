import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

import { Icon } from '../icon/icon';
import { TranslatePipe } from '../../pipes/translate.pipe';

interface NavItem {
  label: string;
  route: string;
  icon: string;
}

interface NavGroup {
  /** Etichetă mică, opțională, deasupra grupului (ex. "BANCAR") — omisă
   * pentru primul și ultimul grup, ca să nu pară "etichetate" inutil. */
  label?: string;
  /** Fundal/border distinct pe TOT grupul (nu doar pe un link) — pentru
   * "Asistenți AI", ca zona întreagă să iasă în evidență ca un bloc
   * coerent, nu un singur rând ciudat. Vezi sidebar__group--highlight. */
  highlight?: boolean;
  items: NavItem[];
}

// Grupate logic (nu o listă plată de 9 linkuri) — Overview e singur, sus,
// ca punct de intrare; restul grupate pe scop, nu pe ordinea în care au
// fost adăugate funcționalitățile.
const NAV_GROUPS: NavGroup[] = [
  {
    items: [{ label: 'nav.overview', route: '/app/overview', icon: 'overview' }],
  },
  {
    label: 'nav.group.banking',
    items: [
      { label: 'nav.accounts', route: '/app/accounts', icon: 'accounts' },
      { label: 'nav.cards', route: '/app/cards', icon: 'cards' },
      { label: 'nav.transactions', route: '/app/transactions', icon: 'transactions' },
      { label: 'nav.transfers', route: '/app/transfers', icon: 'transfer' },
      { label: 'nav.exchange', route: '/app/exchange', icon: 'exchange' },
      { label: 'nav.investments', route: '/app/investments', icon: 'trending-up' },
      { label: 'nav.points', route: '/app/points', icon: 'gift' },
      { label: 'nav.loans', route: '/app/loans', icon: 'banknote' },
    ],
  },
  {
    label: 'nav.group.planning',
    items: [
      { label: 'nav.budgets', route: '/app/budgets', icon: 'budgets' },
      { label: 'nav.forecast', route: '/app/spending-forecast', icon: 'spending' },
    ],
  },
  {
    // Etichetat, ca "Bancar"/"Planificare" mai sus — fără label, grupul
    // ăsta ieșea în evidență ca "orfan" față de restul, inconsecvent
    // vizual, deși cele două intrări sunt deja rudă (ambele agenți AI
    // găzduiți de ai-orchestrator-service).
    label: 'nav.group.assistants',
    highlight: true,
    items: [
      // MaestroAgent (fost "MaestroAssistent") — funcțional acum (agentul
      // Spending + Forecast, peste GPT-5-mini), deci e o intrare normală
      // de navigare, ca oricare alta — NU mai e un card promo în footer.
      // Fără tratament vizual distinct (gradient/border/glow) — userul l-a
      // vrut eliminat, arăta ca un element rupt/inconsecvent față de restul
      // sidebar-ului. Fără insignă "AI" — Support e la fel de mult un
      // agent AI și nu are una, deci ar fi inconsecvent să aibă doar
      // MaestroAgent; grupul ("Asistenți AI") spune deja asta o dată,
      // pentru amândouă, nu are nevoie s-o repete per-element.
      { label: 'nav.copilot', route: '/app/copilot', icon: 'copilot' },
      { label: 'nav.support', route: '/app/support', icon: 'support' },
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
  imports: [RouterLink, RouterLinkActive, Icon, TranslatePipe],
  templateUrl: './sidebar.html',
  styleUrl: './sidebar.css',
})
export class Sidebar {
  protected readonly navGroups = NAV_GROUPS;
}
