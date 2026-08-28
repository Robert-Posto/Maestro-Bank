import { Component, computed, inject, input, signal } from '@angular/core';

import { LanguageService } from '../../../services/language.service';
import { Icon } from '../icon/icon';

export interface SwipeDeckCard {
  kind: 'cover' | 'step' | 'benefit';
  icon?: string;
  step?: number;
  title: string;
  text: string;
}

/**
 * Carte de explicații glisabilă — stânga/dreapta, cu mouse/touch (Pointer
 * Events), săgeți, taste ← → și puncte de navigare directă. Extras din
 * pagina Credite (prima folosire) ca să fie reutilizat identic la Puncte —
 * o singură idee pe card, ca un onboarding real, nu un perete de text.
 *
 * Consumatorul dă doar conținutul (`cards`, `note` opțional); titlul
 * secțiunii ("Cum funcționează...") rămâne la pagina care-l folosește, nu
 * aici, ca fiecare pagină să-și păstreze propriul heading/subtitle.
 */
@Component({
  selector: 'app-swipe-card-deck',
  standalone: true,
  imports: [Icon],
  template: `
    <div class="deck-panel">
      <div class="card-deck" tabindex="0" (keydown.arrowleft)="prev()" (keydown.arrowright)="next()">
        <button type="button" class="card-deck__nav" [attr.aria-label]="language.t('common.previousCard')" (click)="prev()">
          <app-icon name="chevron-left" [size]="18" />
        </button>

        <div
          class="card-deck__viewport"
          (pointerdown)="onPointerDown($event)"
          (pointermove)="onPointerMove($event)"
          (pointerup)="onPointerUp()"
          (pointercancel)="onPointerUp()"
        >
          <div class="card-deck__track" [class.card-deck__track--dragging]="isDragging()" [style.transform]="trackTransform()">
            @for (card of cards(); track $index) {
              <div class="deck-card" [class.deck-card--cover]="card.kind === 'cover'">
                @if (card.kind === 'step') {
                  <span class="deck-card__step">{{ card.step }}</span>
                } @else if (card.kind === 'benefit') {
                  <span class="deck-card__icon"><app-icon [name]="card.icon!" [size]="22" /></span>
                }
                <p class="deck-card__title">{{ card.title }}</p>
                <p class="deck-card__text">{{ card.text }}</p>
              </div>
            }
          </div>
        </div>

        <button type="button" class="card-deck__nav" [attr.aria-label]="language.t('common.nextCard')" (click)="next()">
          <app-icon name="chevron-right" [size]="18" />
        </button>
      </div>

      <div class="card-deck__dots">
        @for (card of cards(); track $index; let i = $index) {
          <button
            type="button"
            class="card-deck__dot"
            [class.card-deck__dot--active]="activeIndex() === i"
            [attr.aria-label]="language.t('common.goToCard').replace('{n}', (i + 1) + '')"
            (click)="goTo(i)"
          ></button>
        }
      </div>

      @if (note()) {
        <p class="deck-panel__note">{{ note() }}</p>
      }

      <ng-content></ng-content>
    </div>
  `,
  styles: [
    `
      .deck-panel {
        background: var(--mb-surface);
        border: 1px solid var(--mb-border);
        border-radius: var(--mb-radius-lg);
        padding: var(--mb-space-8) var(--mb-space-6);
        box-shadow: var(--mb-shadow-sm);
      }

      .card-deck {
        display: flex;
        align-items: center;
        gap: var(--mb-space-4);
        max-width: 640px;
        margin: 0 auto;
        outline: none;
      }

      .card-deck__nav {
        flex-shrink: 0;
        display: grid;
        place-items: center;
        width: 36px;
        height: 36px;
        border-radius: 50%;
        border: 1px solid var(--mb-border);
        background: var(--mb-surface);
        color: var(--mb-text-secondary);
        box-shadow: var(--mb-shadow-xs);
        cursor: pointer;
        transition: all var(--mb-transition-fast);
      }

      .card-deck__nav:hover {
        border-color: var(--mb-blue-500);
        color: var(--mb-blue-600);
        box-shadow: var(--mb-shadow-sm);
        transform: translateY(-1px);
      }

      .card-deck__viewport {
        flex: 1;
        overflow: hidden;
        /* Padding-ul, nu chenarul, dă loc umbrelor cardurilor să respire
           fără să fie tăiate de overflow:hidden (necesar totuși, ca să
           ascundă cardurile vecine în timpul swipe-ului). */
        padding: var(--mb-space-3) 0;
        touch-action: pan-y;
        cursor: grab;
      }

      .card-deck__viewport:active {
        cursor: grabbing;
      }

      .card-deck__track {
        display: flex;
        transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1);
      }

      .card-deck__track--dragging {
        transition: none;
      }

      @media (prefers-reduced-motion: reduce) {
        .card-deck__track {
          transition: none;
        }
      }

      .deck-card {
        flex: 0 0 100%;
        min-height: 260px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        text-align: center;
        gap: var(--mb-space-3);
        padding: var(--mb-space-8) var(--mb-space-6);
        background: var(--mb-surface-muted);
        border: 1px solid var(--mb-border);
        border-radius: var(--mb-radius-lg);
        box-shadow: var(--mb-shadow-md);
        user-select: none;
      }

      .deck-card--cover {
        background: linear-gradient(160deg, var(--mb-info-bg) 0%, var(--mb-surface-muted) 100%);
        border-color: var(--mb-blue-500);
        box-shadow:
          0 10px 28px rgba(47, 111, 237, 0.16),
          var(--mb-shadow-md);
      }

      .deck-card--cover .deck-card__title {
        font-size: var(--mb-font-size-lg);
      }

      .deck-card__step {
        display: grid;
        place-items: center;
        width: 40px;
        height: 40px;
        border-radius: 50%;
        background: var(--mb-blue-600);
        color: #fff;
        font-weight: var(--mb-font-weight-semibold);
      }

      .deck-card__icon {
        display: grid;
        place-items: center;
        width: 44px;
        height: 44px;
        border-radius: 12px;
        background: var(--mb-blue-50);
        color: var(--mb-blue-600);
      }

      .deck-card__title {
        font-size: var(--mb-font-size-md);
        font-weight: var(--mb-font-weight-semibold);
        color: var(--mb-text-primary);
      }

      .deck-card__text {
        font-size: var(--mb-font-size-sm);
        color: var(--mb-text-secondary);
        max-width: 400px;
      }

      .card-deck__dots {
        display: flex;
        justify-content: center;
        align-items: center;
        gap: 6px;
        margin: var(--mb-space-4) 0;
      }

      .card-deck__dot {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        border: none;
        background: var(--mb-border);
        cursor: pointer;
        padding: 0;
        transition: all var(--mb-transition-fast);
      }

      .card-deck__dot--active {
        background: var(--mb-blue-600);
        width: 18px;
        border-radius: var(--mb-radius-pill);
      }

      .deck-panel__note {
        font-size: var(--mb-font-size-xs);
        color: var(--mb-text-tertiary);
        background: var(--mb-surface-muted);
        border-radius: var(--mb-radius-md);
        padding: var(--mb-space-4);
      }

      @media (max-width: 560px) {
        .deck-panel {
          padding: var(--mb-space-6) var(--mb-space-3);
        }
        .card-deck {
          gap: var(--mb-space-2);
        }
      }
    `,
  ],
})
export class SwipeCardDeck {
  protected readonly language = inject(LanguageService);

  readonly cards = input.required<SwipeDeckCard[]>();
  readonly note = input<string>('');

  protected readonly activeIndex = signal(0);
  protected readonly dragOffsetPx = signal(0);
  protected readonly isDragging = signal(false);
  protected readonly trackTransform = computed(() => `translateX(calc(${-this.activeIndex() * 100}% + ${this.dragOffsetPx()}px))`);

  private dragStartX = 0;
  private dragPointerId: number | null = null;

  protected next(): void {
    this.activeIndex.update((i) => (i + 1) % this.cards().length);
  }

  protected prev(): void {
    this.activeIndex.update((i) => (i - 1 + this.cards().length) % this.cards().length);
  }

  protected goTo(index: number): void {
    this.activeIndex.set(index);
  }

  protected onPointerDown(event: PointerEvent): void {
    this.isDragging.set(true);
    this.dragStartX = event.clientX;
    this.dragPointerId = event.pointerId;
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
  }

  protected onPointerMove(event: PointerEvent): void {
    if (!this.isDragging() || event.pointerId !== this.dragPointerId) return;
    this.dragOffsetPx.set(event.clientX - this.dragStartX);
  }

  protected onPointerUp(): void {
    if (!this.isDragging()) return;
    const offset = this.dragOffsetPx();
    const threshold = 60;
    if (offset < -threshold) {
      this.next();
    } else if (offset > threshold) {
      this.prev();
    }
    this.isDragging.set(false);
    this.dragOffsetPx.set(0);
    this.dragPointerId = null;
  }
}
