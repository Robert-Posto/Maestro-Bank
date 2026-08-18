import { Component, OnInit, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';

import { BankingPanel } from './features/banking-panel/banking-panel';
import { ApiService, SystemHealth } from './services/api.service';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, BankingPanel],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App implements OnInit {
  protected readonly title = signal('frontend');

  // --- status arhitectură: Gateway + MongoDB + fiecare microserviciu ---
  protected readonly systemStatus = signal<'checking' | 'ok' | 'degraded' | 'error'>('checking');
  protected readonly mongoStatus = signal<string>('checking');
  protected readonly servicesStatus = signal<Record<string, string>>({});

  constructor(private readonly api: ApiService) {}

  ngOnInit(): void {
    this.checkHealth();
  }

  checkHealth(): void {
    this.systemStatus.set('checking');
    this.mongoStatus.set('checking');

    this.api.getSystemHealth().subscribe({
      next: (health: SystemHealth) => {
        this.systemStatus.set(health.status === 'ok' ? 'ok' : 'degraded');
        this.mongoStatus.set(health.mongodb);
        this.servicesStatus.set(health.services);
      },
      error: () => {
        this.systemStatus.set('error');
        this.mongoStatus.set('error');
        this.servicesStatus.set({});
      },
    });
  }

  protected readonly serviceEntries = () => Object.entries(this.servicesStatus());
}
