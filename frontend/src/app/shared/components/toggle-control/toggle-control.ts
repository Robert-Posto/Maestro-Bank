import { Component, input, output } from '@angular/core';

/** Toggle switch reutilizabil — Card controls (Freeze, Contactless, ATM, etc.). */
@Component({
  selector: 'app-toggle-control',
  standalone: true,
  template: `
    <button
      type="button"
      class="toggle"
      [class.toggle--on]="checked()"
      [disabled]="disabled()"
      role="switch"
      [attr.aria-checked]="checked()"
      (click)="onToggle()"
    >
      <span class="toggle__thumb"></span>
    </button>
  `,
  styles: [
    `
      .toggle {
        width: 44px;
        height: 26px;
        border-radius: var(--mb-radius-pill);
        border: none;
        background: var(--mb-border-strong);
        padding: 3px;
        cursor: pointer;
        display: inline-flex;
        align-items: center;
        transition: background var(--mb-transition-base);
        flex-shrink: 0;
      }
      .toggle--on {
        background: var(--mb-blue-500);
      }
      .toggle:disabled {
        opacity: 0.5;
        cursor: not-allowed;
      }
      .toggle__thumb {
        width: 20px;
        height: 20px;
        border-radius: 50%;
        background: #fff;
        box-shadow: var(--mb-shadow-xs);
        transition: transform var(--mb-transition-base);
      }
      .toggle--on .toggle__thumb {
        transform: translateX(18px);
      }
    `,
  ],
})
export class ToggleControl {
  readonly checked = input(false);
  readonly disabled = input(false);
  readonly toggled = output<boolean>();

  protected onToggle(): void {
    if (this.disabled()) return;
    this.toggled.emit(!this.checked());
  }
}
