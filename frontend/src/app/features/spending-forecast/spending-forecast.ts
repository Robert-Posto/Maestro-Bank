import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { forkJoin } from 'rxjs';

import {
  CashFlowAnalytics,
  ForecastAnalytics,
  SpendingAnalytics,
  TransactionsService,
} from '../../services/transactions.service';
import { LanguageService } from '../../services/language.service';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { StatCard } from '../../shared/components/stat-card/stat-card';
import { LoadingSkeleton } from '../../shared/components/loading-skeleton/loading-skeleton';
import { EmptyState } from '../../shared/components/empty-state/empty-state';
import { MoneyPipe } from '../../shared/pipes/money.pipe';
import { TranslatePipe } from '../../shared/pipes/translate.pipe';
import { categoryColorVar, categoryLabel } from '../../shared/categories';
import { daysUntilBillingLabel } from '../../shared/subscription-display';

interface CategoryBar {
  category: string;
  label: string;
  amountMinor: number;
  percentage: number;
  colorVar: string;
}

interface LinePoint {
  x: number;
  y: number;
  date: string;
  netMinor: number;
}

/**
 * Spending & Forecast — O SINGURĂ pagină (vezi task-ul MaestroBank,
 * secțiunea 16). Analytics determinist, calculat în transactions-service
 * — NU folosește AI. Grafice construite manual (SVG), fără librărie
 * externă, respectând paleta de categorii definită în shared/categories.ts.
 */
@Component({
  selector: 'app-spending-forecast',
  standalone: true,
  imports: [PageHeader, StatCard, LoadingSkeleton, EmptyState, MoneyPipe, DecimalPipe, TranslatePipe],
  templateUrl: './spending-forecast.html',
  styleUrl: './spending-forecast.css',
})
export class SpendingForecast implements OnInit {
  private readonly transactionsApi = inject(TransactionsService);
  private readonly language = inject(LanguageService);

  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);

  protected daysUntilBillingLabel(billingDay: number): string {
    return daysUntilBillingLabel(billingDay, this.language.language());
  }

  protected readonly spending = signal<SpendingAnalytics | null>(null);
  protected readonly cashFlow = signal<CashFlowAnalytics | null>(null);
  protected readonly forecast = signal<ForecastAnalytics | null>(null);

  protected readonly categoryBars = computed<CategoryBar[]>(() => {
    const data = this.spending();
    const language = this.language.language();
    if (!data || data.by_category.length === 0) return [];
    const max = Math.max(...data.by_category.map((c) => c.amount_minor), 1);
    return data.by_category.map((c) => ({
      category: c.category,
      label: categoryLabel(c.category, language),
      amountMinor: c.amount_minor,
      percentage: Math.round((c.amount_minor / max) * 100),
      colorVar: categoryColorVar(c.category),
    }));
  });

  protected readonly cashFlowPath = computed(() => this.buildLinePath());
  protected readonly cashFlowAreaPath = computed(() => this.buildAreaPath());
  protected readonly cashFlowPoints = signal<LinePoint[]>([]);

  ngOnInit(): void {
    this.loading.set(true);
    this.error.set(null);

    forkJoin({
      spending: this.transactionsApi.getSpendingAnalytics(),
      cashFlow: this.transactionsApi.getCashFlowAnalytics(30),
      forecast: this.transactionsApi.getForecastAnalytics(),
    }).subscribe({
      next: ({ spending, cashFlow, forecast }) => {
        this.spending.set(spending);
        this.cashFlow.set(cashFlow);
        this.forecast.set(forecast);
        this.computeLinePoints(cashFlow);
        this.loading.set(false);
      },
      error: () => {
        this.error.set(this.language.t('forecast.loadError'));
        this.loading.set(false);
      },
    });
  }

  private computeLinePoints(data: CashFlowAnalytics): void {
    if (data.points.length === 0) {
      this.cashFlowPoints.set([]);
      return;
    }
    const width = 600;
    const height = 160;
    const netValues = data.points.map((p) => p.net_minor);
    const min = Math.min(...netValues, 0);
    const max = Math.max(...netValues, 0);
    const range = max - min || 1;

    const points = data.points.map((p, index) => {
      const x = data.points.length > 1 ? (index / (data.points.length - 1)) * width : width / 2;
      const y = height - ((p.net_minor - min) / range) * height;
      return { x, y, date: p.date, netMinor: p.net_minor };
    });
    this.cashFlowPoints.set(points);
  }

  private buildLinePath(): string {
    const points = this.cashFlowPoints();
    if (points.length === 0) return '';
    return points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ');
  }

  private buildAreaPath(): string {
    const points = this.cashFlowPoints();
    if (points.length === 0) return '';
    const line = this.buildLinePath();
    const last = points[points.length - 1];
    const first = points[0];
    return `${line} L ${last.x.toFixed(1)} 160 L ${first.x.toFixed(1)} 160 Z`;
  }

  protected zeroLineY(): number {
    const points = this.cashFlowPoints();
    const data = this.cashFlow();
    if (points.length === 0 || !data) return 80;
    const netValues = data.points.map((p) => p.net_minor);
    const min = Math.min(...netValues, 0);
    const max = Math.max(...netValues, 0);
    const range = max - min || 1;
    return 160 - ((0 - min) / range) * 160;
  }
}
