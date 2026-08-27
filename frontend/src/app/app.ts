import { Component, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';

import { RouteLoader } from './shared/components/route-loader/route-loader';
import { LanguageService } from './services/language.service';
import { ThemeService } from './services/theme.service';

/**
 * Root component — pur shell pentru router. Ecranele /login, /register și
 * /app/* (prin AppShell) sunt cele care randează efectiv conținutul.
 *
 * ThemeService e injectat aici (nu doar folosit unde apare toggle-ul) ca
 * să se aplice tema salvată ÎNAINTE de primul randare — altfel ar apărea
 * un flash de temă greșită la încărcarea paginii. LanguageService, la fel,
 * pentru <html lang> — pe FIECARE rută, inclusiv /login (vezi planul
 * fazei de comutator de limbă).
 *
 * RouteLoader e montat o singură dată aici (nu în AppShell) ca să vadă
 * toate navigările, inclusiv intrarea în cont dinspre login/register —
 * dar el decide singur când merită să se arate (vezi comentariul lui:
 * reîncărcare de pagină, intrare în cont, navigare lentă), NU la fiecare
 * schimbare de ecran.
 */
@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, RouteLoader],
  template: `
    <router-outlet />
    <app-route-loader />
  `,
})
export class App {
  private readonly theme = inject(ThemeService);
  private readonly language = inject(LanguageService);
}
