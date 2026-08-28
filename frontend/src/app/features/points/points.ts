import { Component, OnDestroy, OnInit, computed, effect, inject, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';

import {
  EarnRateView,
  PointsService,
  RewardView,
  WheelSegmentView,
  WheelSpinResultView,
} from '../../services/points.service';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { ActionButton } from '../../shared/components/action-button/action-button';
import { Icon } from '../../shared/components/icon/icon';
import { LoadingSkeleton } from '../../shared/components/loading-skeleton/loading-skeleton';
import { EmptyState } from '../../shared/components/empty-state/empty-state';
import { Modal } from '../../shared/components/modal/modal';
import { SwipeCardDeck, SwipeDeckCard } from '../../shared/components/swipe-card-deck/swipe-card-deck';
import { MoneyPipe } from '../../shared/pipes/money.pipe';
import { ToastService } from '../../shared/components/toast/toast.service';
import { extractErrorMessage } from '../../shared/error-utils';
import { TRANSACTION_CATEGORIES, categoryLabel, categoryColorVar } from '../../shared/categories';

/** Cartea de explicații — "Cum funcționează Punctele" — vezi
 * app-swipe-card-deck (aceeași componentă ca la Credite). */
const HOW_POINTS_WORK_CARDS: SwipeDeckCard[] = [
  {
    kind: 'cover',
    title: 'Cum funcționează Punctele MaestroBank',
    text: 'Câștigi, răscumperi sau riști la roată — pe scurt, glisează pentru următorul pas.',
  },
  {
    kind: 'step',
    step: 1,
    title: 'Cumperi de la un comerciant',
    text: 'Orice plată către un cont care nu e al altui user MaestroBank îți dă puncte, ca procent din sumă.',
  },
  {
    kind: 'step',
    step: 2,
    title: 'Rata diferă pe categorie',
    text: 'Vezi tabelul de mai jos — de la 0,5% la facturi, până la 3% la restaurante și shopping.',
  },
  {
    kind: 'step',
    step: 3,
    title: 'Le răscumperi pentru cashback',
    text: 'Alegi o recompensă din catalog — banii intră direct în contul tău curent, nu un voucher simulat.',
  },
  {
    kind: 'step',
    step: 4,
    title: 'Sau le riști la roată',
    text: 'Pariezi puncte pe o învârtire — mai multe puncte pariate, șanse mai bune la premii mai bune.',
  },
  {
    kind: 'benefit',
    icon: 'gift',
    title: '500 de puncte de bun-venit',
    text: 'Primești un bonus doar pentru că ești client MaestroBank — revendică-l mai sus, dacă n-ai făcut-o încă.',
  },
  {
    kind: 'benefit',
    icon: 'unlock',
    title: 'Fără puncte pe transferuri',
    text: 'Doar cumpărăturile reale la comercianți dau puncte — nu și banii trimiși prietenilor.',
  },
  {
    kind: 'benefit',
    icon: 'banknote',
    title: 'Cashback real',
    text: 'Fiecare recompensă înseamnă bani adevărați în cont, creditați instant.',
  },
  {
    kind: 'benefit',
    icon: 'check',
    title: 'Roata e corectă',
    text: 'Rezultatul se decide pe server ÎNAINTE să vezi roata învârtindu-se — nu poate fi manipulat din browser.',
  },
];

/**
 * Puncte de loialitate — câștigate ca procent din plățile către comercianți
 * (NU din transferuri între useri MaestroBank, vezi points-service). Se
 * răscumpără dintr-un catalog fix de recompense (cashback REAL, credit
 * direct în contul curent) sau se pariază la roata norocului — punctele
 * pariate se scad IMEDIAT, indiferent de rezultat (cost real al biletului).
 * Rezultatul roții e decis integral pe server, ÎNAINTE de răspuns —
 * animăm doar roata să se oprească pe segmentul deja decis, niciodată nu
 * calculăm noi rezultatul.
 */
@Component({
  selector: 'app-points',
  standalone: true,
  imports: [
    FormsModule,
    DecimalPipe,
    PageHeader,
    ActionButton,
    Icon,
    LoadingSkeleton,
    EmptyState,
    Modal,
    SwipeCardDeck,
    MoneyPipe,
  ],
  templateUrl: './points.html',
  styleUrl: './points.css',
})
export class Points implements OnInit, OnDestroy {
  private readonly pointsApi = inject(PointsService);
  private readonly toast = inject(ToastService);

  protected readonly categories = TRANSACTION_CATEGORIES;
  protected categoryLabel = categoryLabel;
  protected categoryColorVar = categoryColorVar;
  protected readonly howPointsWorkCards = HOW_POINTS_WORK_CARDS;

  protected readonly balance = signal(0);
  protected readonly balanceLoading = signal(true);
  /** Soldul afișat efectiv — animat spre `balance()` la fiecare schimbare
   * (bonus revendicat, răscumpărare, spin), ca la rata din simulatorul de
   * Credite — numărul "prinde viață" în loc să sară brusc. */
  protected readonly displayedBalance = signal(0);

  protected readonly welcomeBonusClaimed = signal(true);
  protected readonly welcomeBonusPoints = signal(0);
  protected readonly welcomeBonusLoading = signal(true);
  protected readonly claimingWelcomeBonus = signal(false);

  protected readonly earnRates = signal<EarnRateView[]>([]);
  protected readonly earnRatesLoading = signal(true);

  protected readonly rewards = signal<RewardView[]>([]);
  protected readonly rewardsLoading = signal(true);
  protected readonly redeemModalReward = signal<RewardView | null>(null);
  protected readonly redeeming = signal(false);

  protected readonly wheelSegments = signal<WheelSegmentView[]>([]);
  protected readonly wheelLoading = signal(true);
  protected readonly wagerAmount = signal(100);
  protected readonly spinning = signal(false);
  protected readonly spinResult = signal<WheelSpinResultView | null>(null);
  protected readonly wheelRotationDeg = signal(0);

  private readonly SPIN_FULL_TURNS = 6;
  private readonly SPIN_DURATION_MS = 3800;

  protected readonly maxWager = computed(() => this.balance());
  protected readonly prefersReducedMotion = computed(
    () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  );

  private balanceAnimationFrameId: number | null = null;

  constructor() {
    effect(() => this.animateBalanceTo(this.balance()));
  }

  ngOnInit(): void {
    this.loadBalance();
    this.loadEarnRates();
    this.loadRewards();
    this.loadWheelSegments();
    this.loadWelcomeBonusStatus();
  }

  ngOnDestroy(): void {
    if (this.balanceAnimationFrameId !== null) cancelAnimationFrame(this.balanceAnimationFrameId);
  }

  private animateBalanceTo(target: number): void {
    if (this.balanceAnimationFrameId !== null) cancelAnimationFrame(this.balanceAnimationFrameId);
    if (this.prefersReducedMotion()) {
      this.displayedBalance.set(target);
      return;
    }
    const start = this.displayedBalance();
    const startTime = performance.now();
    const duration = 400;
    const step = (now: number) => {
      const t = Math.min(1, (now - startTime) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      this.displayedBalance.set(Math.round(start + (target - start) * eased));
      if (t < 1) {
        this.balanceAnimationFrameId = requestAnimationFrame(step);
      } else {
        this.balanceAnimationFrameId = null;
      }
    };
    this.balanceAnimationFrameId = requestAnimationFrame(step);
  }

  private loadBalance(): void {
    this.balanceLoading.set(true);
    this.pointsApi.getBalance().subscribe({
      next: (result) => {
        this.balance.set(result.balance);
        this.balanceLoading.set(false);
      },
      error: () => this.balanceLoading.set(false),
    });
  }

  private loadEarnRates(): void {
    this.earnRatesLoading.set(true);
    this.pointsApi.getEarnRates().subscribe({
      next: (rates) => {
        this.earnRates.set(rates);
        this.earnRatesLoading.set(false);
      },
      error: () => this.earnRatesLoading.set(false),
    });
  }

  private loadRewards(): void {
    this.rewardsLoading.set(true);
    this.pointsApi.getRewards().subscribe({
      next: (rewards) => {
        this.rewards.set(rewards);
        this.rewardsLoading.set(false);
      },
      error: () => this.rewardsLoading.set(false),
    });
  }

  private loadWheelSegments(): void {
    this.wheelLoading.set(true);
    this.pointsApi.getWheelSegments().subscribe({
      next: (segments) => {
        this.wheelSegments.set(segments);
        this.wheelLoading.set(false);
      },
      error: () => this.wheelLoading.set(false),
    });
  }

  /** Rata unei categorii, deja încărcată — 0 dacă lista încă se încarcă
   * sau categoria nu apare (nu ar trebui, sunt fixe pe backend). */
  protected earnRateFor(category: string): number {
    return this.earnRates().find((r) => r.category === category)?.rate_percent ?? 0;
  }

  // --- Bonus de bun-venit -------------------------------------------------------------

  private loadWelcomeBonusStatus(): void {
    this.welcomeBonusLoading.set(true);
    this.pointsApi.getWelcomeBonusStatus().subscribe({
      next: (result) => {
        this.welcomeBonusClaimed.set(result.claimed);
        this.welcomeBonusPoints.set(result.bonus_points);
        this.welcomeBonusLoading.set(false);
      },
      error: () => this.welcomeBonusLoading.set(false),
    });
  }

  protected claimWelcomeBonus(): void {
    if (this.claimingWelcomeBonus() || this.welcomeBonusClaimed()) return;

    this.claimingWelcomeBonus.set(true);
    this.pointsApi.claimWelcomeBonus().subscribe({
      next: (result) => {
        this.claimingWelcomeBonus.set(false);
        this.welcomeBonusClaimed.set(true);
        this.balance.set(result.new_balance);
        this.toast.success(`Ai primit ${result.points_awarded} puncte de bun-venit!`);
        this.loadRewards();
      },
      error: (err) => {
        this.claimingWelcomeBonus.set(false);
        this.toast.error(extractErrorMessage(err, 'Revendicarea bonusului a eșuat.'));
      },
    });
  }

  // --- Recompense ----------------------------------------------------------------

  protected openRedeemConfirm(reward: RewardView): void {
    if (!reward.affordable) return;
    this.redeemModalReward.set(reward);
  }

  protected closeRedeemConfirm(): void {
    if (this.redeeming()) return;
    this.redeemModalReward.set(null);
  }

  protected confirmRedeem(): void {
    const reward = this.redeemModalReward();
    if (!reward) return;

    this.redeeming.set(true);
    this.pointsApi.redeemReward(reward.id).subscribe({
      next: (result) => {
        this.redeeming.set(false);
        this.redeemModalReward.set(null);
        this.balance.set(result.new_balance);
        this.toast.success(`Ai răscumpărat "${reward.title}" — ${(result.ron_credited_minor / 100).toFixed(2)} lei creditați în cont.`);
        this.loadRewards();
      },
      error: (err) => {
        this.redeeming.set(false);
        this.toast.error(extractErrorMessage(err, 'Răscumpărarea a eșuat.'));
      },
    });
  }

  // --- Roata norocului ----------------------------------------------------------------

  /** Unghiul (0 = sus, crește în sensul acelor de ceasornic) al centrului
   * segmentului `index`, din N segmente totale — folosit ATÂT pentru
   * desenarea feliei (wedgePath), CÂT ȘI pentru calculul rotației finale
   * la spin (finalRotationDeg), ca cele două să rămână mereu consistente. */
  private segmentCenterAngle(index: number, total: number): number {
    const anglePer = 360 / total;
    return index * anglePer + anglePer / 2;
  }

  private polarToCartesian(cx: number, cy: number, r: number, angleDeg: number): { x: number; y: number } {
    const rad = (angleDeg * Math.PI) / 180;
    return { x: cx + r * Math.sin(rad), y: cy - r * Math.cos(rad) };
  }

  /** Path SVG pentru felia `index` a roții (viewBox 0 0 100 100, centru
   * 50,50, rază 48) — geometrie calculată în TS, la fel ca sparkline-ul de
   * la Investiții. */
  protected wedgePath(index: number): string {
    const total = this.wheelSegments().length;
    if (total === 0) return '';
    const anglePer = 360 / total;
    const start = this.polarToCartesian(50, 50, 48, index * anglePer);
    const end = this.polarToCartesian(50, 50, 48, (index + 1) * anglePer);
    const largeArc = anglePer > 180 ? 1 : 0;
    return `M 50,50 L ${start.x.toFixed(2)},${start.y.toFixed(2)} A 48,48 0 ${largeArc},1 ${end.x.toFixed(2)},${end.y.toFixed(2)} Z`;
  }

  /** Poziția etichetei unei felii (la 70% din rază, spre marginea ei) —
   * ca textul să nu se suprapună peste centru. */
  protected labelPosition(index: number): { x: number; y: number } {
    const total = this.wheelSegments().length;
    if (total === 0) return { x: 50, y: 50 };
    const point = this.polarToCartesian(50, 50, 34, this.segmentCenterAngle(index, total));
    return { x: point.x, y: point.y };
  }

  /** Culoarea unei felii — reciclăm paletele deja definite pentru
   * categoriile de tranzacții (--mb-cat-*), fără să inventăm tokens noi. */
  protected segmentFill(index: number): string {
    const colorVar = this.categories[index % this.categories.length]?.colorVar ?? '--mb-cat-other';
    return `var(${colorVar})`;
  }

  protected setWager(value: number): void {
    this.wagerAmount.set(Math.max(1, Math.min(value || 1, this.maxWager() || 1)));
  }

  protected spin(): void {
    const wager = this.wagerAmount();
    if (wager <= 0 || wager > this.balance() || this.spinning()) return;

    this.spinning.set(true);
    this.spinResult.set(null);

    this.pointsApi.spin(wager).subscribe({
      next: (result) => {
        // Rezultatul e DEJA decis de server — doar animăm roata până acolo.
        const segments = this.wheelSegments();
        const winningIndex = segments.findIndex((s) => s.id === result.winning_segment_id);
        if (winningIndex === -1 || this.prefersReducedMotion()) {
          // Segment necunoscut (n-ar trebui) sau reduced-motion — arătăm
          // direct rezultatul, fără animație.
          this.balance.set(result.new_balance);
          this.spinResult.set(result);
          this.spinning.set(false);
          this.loadRewards();
          return;
        }

        const targetAngle = this.segmentCenterAngle(winningIndex, segments.length);
        const targetMod = (360 - (targetAngle % 360)) % 360;
        const currentMod = ((this.wheelRotationDeg() % 360) + 360) % 360;
        const forwardDelta = (targetMod - currentMod + 360) % 360;
        this.wheelRotationDeg.update((current) => current + this.SPIN_FULL_TURNS * 360 + forwardDelta);

        setTimeout(() => {
          this.balance.set(result.new_balance);
          this.spinResult.set(result);
          this.spinning.set(false);
          this.loadRewards();
        }, this.SPIN_DURATION_MS);
      },
      error: (err) => {
        this.spinning.set(false);
        this.toast.error(extractErrorMessage(err, 'Învârtirea a eșuat.'));
      },
    });
  }

  protected closeSpinResult(): void {
    this.spinResult.set(null);
  }
}
