import { Component, input } from '@angular/core';

/** Skeleton discret pentru stările de loading — nu afișa niciodată JSON brut sau un spinner sec. */
@Component({
  selector: 'app-loading-skeleton',
  standalone: true,
  template: `
    <div class="skeleton-stack" [style.gap.px]="gap()">
      @for (row of rowsArray(); track $index) {
        <div class="skeleton-row" [style.height.px]="height()" [style.width]="$index === rowsArray().length - 1 ? lastWidth() : '100%'"></div>
      }
    </div>
  `,
  styles: [
    `
      .skeleton-stack {
        display: flex;
        flex-direction: column;
      }
      .skeleton-row {
        border-radius: var(--mb-radius-sm);
        background: linear-gradient(90deg, var(--mb-surface-muted) 25%, var(--mb-border) 37%, var(--mb-surface-muted) 63%);
        background-size: 400% 100%;
        animation: skeleton-shimmer 1.4s ease infinite;
      }
      @keyframes skeleton-shimmer {
        0% {
          background-position: 100% 50%;
        }
        100% {
          background-position: 0 50%;
        }
      }
      @media (prefers-reduced-motion: reduce) {
        .skeleton-row {
          animation: none;
        }
      }
    `,
  ],
})
export class LoadingSkeleton {
  readonly rows = input(3);
  readonly height = input(16);
  readonly gap = input(10);
  readonly lastWidth = input('70%');

  protected rowsArray(): number[] {
    return Array.from({ length: this.rows() });
  }
}
