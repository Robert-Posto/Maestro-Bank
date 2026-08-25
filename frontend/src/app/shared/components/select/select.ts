import { Component, ElementRef, HostListener, computed, inject, input, output, signal } from '@angular/core';

import { Icon } from '../icon/icon';

export interface SelectOption {
  value: string;
  label: string;
  /** Token CSS (ex. "--mb-cat-groceries") pentru punctul colorat din stânga etichetei — opțional. */
  colorVar?: string;
}

/**
 * Dropdown custom, complet stilizat cu tokenii aplicației — înlocuiește
 * `<select>` nativ acolo unde popup-ul lui (controlat de browser/OS, NU de
 * CSS-ul aplicației) arăta "vechi" și avea contrast prost în dark mode
 * (browserul decide culorile listei de opțiuni, nu tokenii --mb-*, vezi
 * styles.css::color-scheme). Dimensionat identic cu app-action-button
 * (același padding/font/radius), ca să nu mai iasă în evidență lângă
 * celelalte butoane dintr-o bară de filtre/acțiuni.
 */
@Component({
  selector: 'app-select',
  standalone: true,
  imports: [Icon],
  template: `
    <div class="mb-select">
      <button
        type="button"
        class="mb-select__trigger"
        [class.mb-select__trigger--bare]="variant() === 'bare'"
        [class.mb-select__trigger--open]="open()"
        (click)="toggle()"
      >
        @if (selected()?.colorVar) {
          <span class="mb-select__dot" [style.background]="'var(' + selected()!.colorVar + ')'"></span>
        }
        <span class="mb-select__label">{{ selected()?.label ?? placeholder() }}</span>
        <app-icon name="chevron-down" [size]="14" class="mb-select__chevron" />
      </button>

      @if (open()) {
        <div class="mb-select__panel" role="listbox">
          @for (option of options(); track option.value) {
            <button
              type="button"
              class="mb-select__option"
              role="option"
              [class.mb-select__option--active]="option.value === value()"
              [attr.aria-selected]="option.value === value()"
              (click)="pick(option)"
            >
              @if (option.colorVar) {
                <span class="mb-select__dot" [style.background]="'var(' + option.colorVar + ')'"></span>
              }
              <span class="mb-select__label">{{ option.label }}</span>
              @if (option.value === value()) {
                <app-icon name="check" [size]="14" class="mb-select__check" />
              }
            </button>
          }
        </div>
      }
    </div>
  `,
  styles: [
    `
      .mb-select {
        position: relative;
      }

      .mb-select__trigger {
        display: inline-flex;
        align-items: center;
        gap: var(--mb-space-2);
        width: 100%;
        font-family: inherit;
        font-size: var(--mb-font-size-sm);
        font-weight: var(--mb-font-weight-medium);
        color: var(--mb-text-primary);
        background: var(--mb-surface);
        border: 1px solid var(--mb-border-strong);
        border-radius: var(--mb-radius-sm);
        padding: 0.65rem 1.1rem;
        cursor: pointer;
        transition: border-color var(--mb-transition-fast), box-shadow var(--mb-transition-fast);
      }

      .mb-select__trigger:hover {
        border-color: var(--mb-blue-500);
      }

      .mb-select__trigger--open {
        border-color: var(--mb-blue-500);
        box-shadow: 0 0 0 3px rgba(47, 111, 237, 0.1);
      }

      /* Fără chenar/fundal propriu — pentru cuiburi într-un container deja
         stilizat (ex. fx-field__row din Exchange), ca să nu apară "cutie în
         cutie". Culoarea de focus rămâne vizibilă prin text, nu prin ring. */
      .mb-select__trigger--bare {
        border: none;
        background: transparent;
        padding: 0.3rem 0.5rem 0.3rem 0.3rem;
        border-radius: var(--mb-radius-pill);
      }

      .mb-select__trigger--bare:hover {
        background: var(--mb-surface-muted);
      }

      .mb-select__trigger--bare.mb-select__trigger--open {
        background: var(--mb-surface-muted);
        box-shadow: none;
      }

      .mb-select__label {
        flex: 1;
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        text-align: left;
      }

      .mb-select__chevron {
        flex-shrink: 0;
        color: var(--mb-text-tertiary);
        transition: transform var(--mb-transition-fast);
      }

      .mb-select__trigger--open .mb-select__chevron {
        transform: rotate(180deg);
      }

      .mb-select__dot {
        flex-shrink: 0;
        width: 8px;
        height: 8px;
        border-radius: 50%;
      }

      .mb-select__panel {
        position: absolute;
        z-index: 30;
        top: calc(100% + 6px);
        left: 0;
        min-width: 100%;
        max-height: 280px;
        overflow-y: auto;
        background: var(--mb-surface);
        border: 1px solid var(--mb-border);
        border-radius: var(--mb-radius-md);
        box-shadow: var(--mb-shadow-md);
        padding: var(--mb-space-2);
        display: flex;
        flex-direction: column;
        gap: 2px;
        animation: mb-select-in 140ms ease;
      }

      @keyframes mb-select-in {
        from {
          opacity: 0;
          transform: translateY(-4px);
        }
        to {
          opacity: 1;
          transform: translateY(0);
        }
      }

      .mb-select__option {
        display: flex;
        align-items: center;
        gap: var(--mb-space-2);
        width: 100%;
        font-family: inherit;
        font-size: var(--mb-font-size-sm);
        color: var(--mb-text-primary);
        background: transparent;
        border: none;
        border-radius: var(--mb-radius-sm);
        padding: 0.55rem var(--mb-space-3);
        cursor: pointer;
        text-align: left;
        white-space: nowrap;
      }

      .mb-select__option:hover {
        background: var(--mb-surface-muted);
      }

      .mb-select__option--active {
        font-weight: var(--mb-font-weight-medium);
        color: var(--mb-blue-600);
      }

      .mb-select__check {
        margin-left: auto;
        flex-shrink: 0;
        color: var(--mb-blue-600);
      }

      @media (prefers-reduced-motion: reduce) {
        .mb-select__panel {
          animation: none;
        }
      }
    `,
  ],
})
export class Select {
  readonly options = input.required<SelectOption[]>();
  readonly value = input<string>('');
  readonly placeholder = input<string>('Alege');
  /** 'bare' = fără chenar/fundal propriu, pentru cuiburi într-un container deja stilizat. */
  readonly variant = input<'field' | 'bare'>('field');
  readonly changed = output<string>();

  private readonly elementRef = inject(ElementRef<HTMLElement>);
  protected readonly open = signal(false);

  protected readonly selected = computed(() => this.options().find((o) => o.value === this.value()) ?? null);

  protected toggle(): void {
    this.open.update((o) => !o);
  }

  protected pick(option: SelectOption): void {
    this.open.set(false);
    if (option.value !== this.value()) {
      this.changed.emit(option.value);
    }
  }

  @HostListener('document:click', ['$event'])
  protected onDocumentClick(event: MouseEvent): void {
    if (!this.open()) return;
    if (!this.elementRef.nativeElement.contains(event.target as Node)) {
      this.open.set(false);
    }
  }

  @HostListener('document:keydown.escape')
  protected onEscape(): void {
    this.open.set(false);
  }
}
