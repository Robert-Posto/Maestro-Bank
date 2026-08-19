import { Component, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';

import { ThemeService } from './services/theme.service';

/**
 * Root component — pur shell pentru router. Ecranele /login, /register și
 * /app/* (prin AppShell) sunt cele care randează efectiv conținutul.
 *
 * ThemeService e injectat aici (nu doar folosit unde apare toggle-ul) ca
 * să se aplice tema salvată ÎNAINTE de primul randare — altfel ar apărea
 * un flash de temă greșită la încărcarea paginii.
 */
@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet],
  template: `<router-outlet />`,
})
export class App {
  private readonly theme = inject(ThemeService);
}
