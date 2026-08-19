import { Component, computed, input } from '@angular/core';

import { merchantBadge } from '../../merchant-logo';
import { categoryColorVar } from '../../categories';

export type MerchantAvatarSize = 'sm' | 'md' | 'lg';

/**
 * Insignă de comerciant — vezi UI reference/Transactions.png. Dacă
 * `description` se potrivește cu un comerciant cunoscut (shared/merchant-logo.ts),
 * arată eticheta + culoarea de brand (ex. Kaufland → roșu, "K"). Altfel
 * cade pe inițiale colorate: navy dacă e un transfer real către alt user
 * MaestroBank (`isPerson`), sau culoarea categoriei (aceeași paletă ca la
 * Bugete/Spending) pentru un comerciant necunoscut.
 */
@Component({
  selector: 'app-merchant-avatar',
  standalone: true,
  template: `
    <span
      class="merchant-avatar"
      [class.merchant-avatar--sm]="size() === 'sm'"
      [class.merchant-avatar--lg]="size() === 'lg'"
      [style.background]="background()"
      [style.color]="foreground()"
    >
      {{ label() }}
    </span>
  `,
  styles: [
    `
      .merchant-avatar {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 36px;
        height: 36px;
        border-radius: var(--mb-radius-sm);
        font-size: 0.7rem;
        font-weight: var(--mb-font-weight-semibold);
        letter-spacing: -0.01em;
        flex-shrink: 0;
        overflow: hidden;
        white-space: nowrap;
      }
      .merchant-avatar--sm {
        width: 28px;
        height: 28px;
        font-size: 0.62rem;
      }
      .merchant-avatar--lg {
        width: 52px;
        height: 52px;
        font-size: 0.9rem;
        border-radius: var(--mb-radius-md);
      }
    `,
  ],
})
export class MerchantAvatar {
  readonly name = input.required<string>();
  readonly description = input<string | null | undefined>(null);
  readonly isPerson = input(false);
  readonly category = input<string | null | undefined>(null);
  readonly size = input<MerchantAvatarSize>('md');

  protected readonly badge = computed(() => (this.isPerson() ? null : merchantBadge(this.description())));

  protected readonly initials = computed(() => {
    const parts = this.name().trim().split(/\s+/).filter(Boolean);
    if (parts.length === 0) return '?';
    return (parts[0].charAt(0) + (parts[1]?.charAt(0) ?? '')).toUpperCase();
  });

  protected readonly label = computed(() => this.badge()?.label ?? this.initials());

  protected readonly background = computed(() => {
    const badge = this.badge();
    if (badge) return badge.bg;
    if (this.isPerson()) return 'var(--mb-navy-900)';
    return `color-mix(in srgb, var(${categoryColorVar(this.category())}) 16%, white)`;
  });

  protected readonly foreground = computed(() => {
    const badge = this.badge();
    if (badge) return badge.fg;
    if (this.isPerson()) return '#ffffff';
    return `var(${categoryColorVar(this.category())})`;
  });
}
