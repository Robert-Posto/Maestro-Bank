import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';

/**
 * Root component — pur shell pentru router. Ecranele /login, /register și
 * /app/* (prin AppShell) sunt cele care randează efectiv conținutul.
 */
@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet],
  template: `<router-outlet />`,
})
export class App {}
