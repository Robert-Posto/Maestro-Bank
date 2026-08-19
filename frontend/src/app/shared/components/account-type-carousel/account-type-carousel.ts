import { Component, ElementRef, signal, input, output, viewChild } from '@angular/core';

import { AccountType } from '../../../services/banking.service';
import { AccountTypeMeta } from '../../account-types';
import { Icon } from '../icon/icon';
import { ActionButton } from '../action-button/action-button';

export interface AccountCreateEvent {
  type: AccountType;
  documentFilename: string | null;
}

/**
 * Carusel "swipe" cu tipurile de cont disponibile de deschis — vezi
 * Accounts feature. Un card pe "pagină" (scroll-snap orizontal): swipe pe
 * mobil, scroll orizontal de trackpad pe laptop, sau săgeți/puncte pentru
 * navigare cu mouse-ul. Fiecare card are propriul buton "Deschide cont" —
 * nu depinde de "care card e centrat acum". Cardurile care cer un
 * document (ex. student) au propriul selector de fișier inline; butonul
 * rămâne dezactivat până la atașarea unui fișier.
 */
@Component({
  selector: 'app-account-type-carousel',
  standalone: true,
  imports: [Icon, ActionButton],
  template: `
    <div class="atc">
      <div class="atc__track" #track (scroll)="onScroll()">
        @for (t of types(); track t.type) {
          <article class="atc__card">
            <span class="atc__icon" [style.color]="'var(' + t.colorVar + ')'" [style.background]="'color-mix(in srgb, var(' + t.colorVar + ') 14%, white)'">
              <app-icon [name]="t.icon" [size]="26" />
            </span>
            <h3>{{ t.label }}</h3>
            <p class="atc__tagline">{{ t.tagline }}</p>
            <span class="atc__rate" [style.color]="'var(' + t.colorVar + ')'">{{ t.rateLabel }}</span>
            <ul class="atc__benefits">
              @for (b of t.benefits; track b) {
                <li><app-icon name="check" [size]="13" />{{ b }}</li>
              }
            </ul>

            @if (t.requiresDocument) {
              <label class="atc__dropzone" [class.atc__dropzone--filled]="!!fileNames()[t.type]">
                <input type="file" (change)="onFileSelected(t.type, $event)" accept=".pdf,.jpg,.jpeg,.png" />
                <app-icon [name]="fileNames()[t.type] ? 'check' : 'download'" [size]="16" />
                <span>{{ fileNames()[t.type] || 'Atașează document (PDF/imagine)' }}</span>
              </label>
              <p class="atc__document-hint">{{ t.documentHint }}</p>
            }

            <app-action-button
              [fullWidth]="true"
              [disabled]="!!t.requiresDocument && !fileNames()[t.type]"
              [loading]="creatingType() === t.type"
              (pressed)="submit(t)"
            >
              Deschide {{ t.label.toLowerCase() }}
            </app-action-button>
          </article>
        }
      </div>

      @if (types().length > 1) {
        <div class="atc__nav">
          <button type="button" class="atc__arrow" aria-label="Anterior" [disabled]="activeIndex() === 0" (click)="goTo(activeIndex() - 1)">
            <span class="atc__arrow-icon atc__arrow-icon--prev"><app-icon name="chevron-right" [size]="16" /></span>
          </button>
          <div class="atc__dots">
            @for (t of types(); track t.type; let i = $index) {
              <button
                type="button"
                class="atc__dot"
                [class.atc__dot--active]="activeIndex() === i"
                [attr.aria-label]="'Vezi ' + t.label"
                (click)="goTo(i)"
              ></button>
            }
          </div>
          <button type="button" class="atc__arrow" aria-label="Următorul" [disabled]="activeIndex() === types().length - 1" (click)="goTo(activeIndex() + 1)">
            <app-icon name="chevron-right" [size]="16" />
          </button>
        </div>
      }
    </div>
  `,
  styleUrl: './account-type-carousel.css',
})
export class AccountTypeCarousel {
  readonly types = input.required<AccountTypeMeta[]>();
  readonly creatingType = input<AccountType | null>(null);
  readonly create = output<AccountCreateEvent>();

  private readonly track = viewChild<ElementRef<HTMLElement>>('track');
  protected readonly activeIndex = signal(0);
  protected readonly fileNames = signal<Partial<Record<AccountType, string>>>({});
  private scrollTimeout?: ReturnType<typeof setTimeout>;

  protected onFileSelected(type: AccountType, event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    this.fileNames.update((map) => ({ ...map, [type]: file?.name ?? '' }));
  }

  protected submit(t: AccountTypeMeta): void {
    this.create.emit({ type: t.type, documentFilename: this.fileNames()[t.type] ?? null });
  }

  protected onScroll(): void {
    if (this.scrollTimeout) clearTimeout(this.scrollTimeout);
    this.scrollTimeout = setTimeout(() => {
      const el = this.track()?.nativeElement;
      if (!el || el.clientWidth === 0) return;
      const index = Math.round(el.scrollLeft / el.clientWidth);
      this.activeIndex.set(Math.min(Math.max(index, 0), this.types().length - 1));
    }, 80);
  }

  protected goTo(index: number): void {
    const el = this.track()?.nativeElement;
    if (!el || index < 0 || index >= this.types().length) return;
    el.scrollTo({ left: index * el.clientWidth, behavior: 'smooth' });
    this.activeIndex.set(index);
  }
}
