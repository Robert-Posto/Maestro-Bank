import { Component, input } from '@angular/core';

import { Icon } from '../icon/icon';

export type StatTrend = 'up' | 'down' | 'neutral';

/** Card de KPI (valoare + etichetă + trend opțional). */
@Component({
  selector: 'app-stat-card',
  standalone: true,
  imports: [Icon],
  template: `
    <div class="stat-card" [class.stat-card--flush]="flush()">
      <div class="stat-card__row">
        <span class="stat-card__label">{{ label() }}</span>
        @if (icon()) {
          <span class="stat-card__icon" [class]="'stat-card__icon--' + iconTone()">
            <app-icon [name]="icon()!" [size]="17" />
          </span>
        }
      </div>
      <div class="stat-card__value">{{ value() }}</div>
      @if (trendText()) {
        <div class="stat-card__trend" [class]="'stat-card__trend--' + trend()">{{ trendText() }}</div>
      }
      <ng-content />
    </div>
  `,
  styles: [
    `
      .stat-card {
        background: var(--mb-surface);
        border: 1px solid var(--mb-border);
        border-radius: var(--mb-radius-lg);
        padding: var(--mb-space-5);
        box-shadow: var(--mb-shadow-xs);
        display: flex;
        flex-direction: column;
        gap: var(--mb-space-2);
        min-width: 0;
      }
      /* Pentru situația în care mai multe stat-card-uri stau într-un rând
         unificat (o singură cutie cu divizoare) — wrapper-ul din pagina
         consumatoare oferă bordura/radius-ul/shadow-ul exterior (vezi
         spending-forecast.css::.sf-stats). Fundalul NU se elimină aici —
         wrapper-ul folosește trucul clasic "gap: 1px + background pe
         culoarea bordurii" ca gap-ul să devină un divizor subțire între
         carduri; asta cere ca fiecare card să rămână OPAC (moștenește
         var(--mb-surface) de la .stat-card mai sus), altfel gri-ul
         wrapper-ului se vede peste tot, nu doar prin gap — exact bug-ul
         raportat ("panelul de sus e gri și arată ciudat"). */
      .stat-card--flush {
        border: none;
        border-radius: 0;
        box-shadow: none;
      }
      .stat-card__row {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: var(--mb-space-2);
      }
      .stat-card__label {
        font-size: var(--mb-font-size-sm);
        color: var(--mb-text-secondary);
      }
      .stat-card__icon {
        width: 34px;
        height: 34px;
        border-radius: var(--mb-radius-sm);
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 1rem;
        flex-shrink: 0;
      }
      .stat-card__icon--blue {
        background: var(--mb-blue-50);
        color: var(--mb-blue-600);
      }
      .stat-card__icon--red {
        background: var(--mb-negative-bg);
        color: var(--mb-negative);
      }
      .stat-card__icon--green {
        background: var(--mb-positive-bg);
        color: var(--mb-positive);
      }
      .stat-card__value {
        font-size: var(--mb-font-size-2xl);
        font-weight: var(--mb-font-weight-semibold);
        letter-spacing: -0.01em;
        overflow-wrap: anywhere;
      }
      .stat-card__trend {
        font-size: var(--mb-font-size-xs);
        font-weight: var(--mb-font-weight-medium);
      }
      .stat-card__trend--up {
        color: var(--mb-positive);
      }
      .stat-card__trend--down {
        color: var(--mb-negative);
      }
      .stat-card__trend--neutral {
        color: var(--mb-text-tertiary);
      }
    `,
  ],
})
export class StatCard {
  readonly label = input.required<string>();
  readonly value = input.required<string>();
  readonly icon = input<string | undefined>(undefined);
  readonly iconTone = input<'blue' | 'red' | 'green'>('blue');
  readonly trendText = input<string | undefined>(undefined);
  readonly trend = input<StatTrend>('neutral');
  readonly flush = input(false);
}
