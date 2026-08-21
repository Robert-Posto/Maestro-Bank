import { Component } from '@angular/core';

import { PageHeader } from '../../shared/components/page-header/page-header';
import { Icon } from '../../shared/components/icon/icon';

/**
 * AI Copilot — construit vizual pentru consistență cu restul aplicației
 * (vezi UI reference/AI copilot.png), dar FĂRĂ nicio integrare AI reală
 * (NU OpenAI, NU Azure Foundry, NU agenți, NU orchestrator). Vezi
 * task-ul MaestroBank, secțiunea 23. Chat input dezactivat intenționat —
 * nu generăm răspunsuri false care ar părea produse de un AI real.
 *
 * Support Agent (backend/ai-orchestrator-service) e conectat la pagina
 * Suport (vezi features/support/support.ts), NU aici — MaestroAssistent
 * e rezervat pentru un agent viitor (Spending + Forecast).
 */
@Component({
  selector: 'app-copilot',
  standalone: true,
  imports: [PageHeader, Icon],
  templateUrl: './copilot.html',
  styleUrl: './copilot.css',
})
export class Copilot {}
