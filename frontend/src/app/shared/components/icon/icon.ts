import { Component, input } from '@angular/core';

/**
 * Set de iconițe minimaliste (line-icons, stroke=currentColor) — folosit
 * peste tot în loc de emoji (vezi task-ul MaestroBank, secțiunea 3: "NU
 * vreau emoji"). Adaugă un nou `case` aici dacă mai e nevoie de o
 * iconiță — nu inserta SVG inline în componente.
 */
@Component({
  selector: 'app-icon',
  standalone: true,
  template: `
    <svg
      [attr.width]="size()"
      [attr.height]="size()"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      [attr.stroke-width]="strokeWidth()"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
    >
      @switch (name()) {
        @case ('overview') {
          <rect x="3" y="3" width="7" height="9" rx="1.5" />
          <rect x="14" y="3" width="7" height="5" rx="1.5" />
          <rect x="14" y="12" width="7" height="9" rx="1.5" />
          <rect x="3" y="16" width="7" height="5" rx="1.5" />
        }
        @case ('accounts') {
          <rect x="3" y="6" width="18" height="13" rx="2" />
          <path d="M3 10h18" />
          <circle cx="16.5" cy="14.5" r="1.4" fill="currentColor" stroke="none" />
        }
        @case ('cards') {
          <rect x="2.5" y="5" width="19" height="14" rx="2.5" />
          <path d="M2.5 9.5h19" />
          <path d="M6 14.5h5" />
        }
        @case ('transactions') {
          <path d="M4 6h16" />
          <path d="M4 12h10" />
          <path d="M4 18h13" />
        }
        @case ('transfer') {
          <path d="M4 7h13" />
          <path d="M13 3l4 4-4 4" />
          <path d="M20 17H7" />
          <path d="M11 21l-4-4 4-4" />
        }
        @case ('exchange') {
          <circle cx="12" cy="12" r="9" />
          <path d="M8.5 10.5c.7-1.3 2-2 3.5-2s3 .9 3.5 2" />
          <path d="M15.5 13.5c-.7 1.3-2 2-3.5 2s-3-.9-3.5-2" />
          <path d="M15 8.5v2h-2" />
          <path d="M9 15.5v-2h2" />
        }
        @case ('budgets') {
          <circle cx="12" cy="12" r="9" />
          <path d="M12 3v9l6.5 4.5" />
        }
        @case ('spending') {
          <path d="M4 19V5" />
          <path d="M4 19h16" />
          <path d="M7 15l4-4 3 3 5-6" />
        }
        @case ('support') {
          <circle cx="12" cy="12" r="9" />
          <path d="M9.2 9.5a2.8 2.8 0 1 1 3.9 2.6c-.9.5-1.3 1-1.3 2" />
          <circle cx="12" cy="16.8" r="0.3" fill="currentColor" />
        }
        @case ('copilot') {
          <path
            d="M12 3l1.5 4.2L18 9l-4.5 1.8L12 15l-1.5-4.2L6 9l4.5-1.8L12 3z"
          />
          <path d="M19 15l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7.7-2z" />
        }
        @case ('profile') {
          <circle cx="12" cy="8" r="3.5" />
          <path d="M4.5 20c1.4-3.6 4.4-5.5 7.5-5.5s6.1 1.9 7.5 5.5" />
        }
        @case ('logout') {
          <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
          <path d="M16 17l5-5-5-5" />
          <path d="M21 12H9" />
        }
        @case ('search') {
          <circle cx="11" cy="11" r="7" />
          <path d="M21 21l-4.3-4.3" />
        }
        @case ('bell') {
          <path d="M6 10a6 6 0 1 1 12 0c0 4 1.5 5.5 1.5 5.5H4.5S6 14 6 10z" />
          <path d="M10 19a2 2 0 0 0 4 0" />
        }
        @case ('chevron-right') {
          <path d="M9 6l6 6-6 6" />
        }
        @case ('chevron-left') {
          <path d="M15 6l-6 6 6 6" />
        }
        @case ('chevron-down') {
          <path d="M6 9l6 6 6-6" />
        }
        @case ('eye') {
          <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" />
          <circle cx="12" cy="12" r="3" />
        }
        @case ('eye-off') {
          <path d="M3 3l18 18" />
          <path d="M10.6 5.7A10.6 10.6 0 0 1 12 5.5c6 0 9.5 6.5 9.5 6.5a15.6 15.6 0 0 1-3.4 4.2" />
          <path d="M6.2 6.9C3.7 8.6 2.5 12 2.5 12s3.5 6.5 9.5 6.5c1.3 0 2.5-.3 3.6-.8" />
          <path d="M9.9 10a3 3 0 0 0 4.1 4.1" />
        }
        @case ('flash') {
          <path d="M13 2 4 14h6l-1 8 9-12h-6l1-8z" />
        }
        @case ('close') {
          <path d="M6 6l12 12" />
          <path d="M18 6L6 18" />
        }
        @case ('check') {
          <path d="M5 12.5l4.5 4.5L19 7" />
        }
        @case ('copy') {
          <rect x="9" y="9" width="11" height="11" rx="2" />
          <path d="M5 15V5a2 2 0 0 1 2-2h10" />
        }
        @case ('plus') {
          <path d="M12 5v14" />
          <path d="M5 12h14" />
        }
        @case ('trash') {
          <path d="M4 7h16" />
          <path d="M9 7V4h6v3" />
          <path d="M6 7l1 13h10l1-13" />
        }
        @case ('edit') {
          <path d="M4 20l1-4L16.5 4.5a2 2 0 0 1 3 3L8 19l-4 1z" />
        }
        @case ('filter') {
          <path d="M4 5h16" />
          <path d="M7 12h10" />
          <path d="M10 19h4" />
        }
        @case ('download') {
          <path d="M12 3v13" />
          <path d="M7 11l5 5 5-5" />
          <path d="M4 21h16" />
        }
        @case ('lock') {
          <rect x="5" y="11" width="14" height="9" rx="2" />
          <path d="M8 11V7a4 4 0 0 1 8 0v4" />
        }
        @case ('unlock') {
          <rect x="5" y="11" width="14" height="9" rx="2" />
          <path d="M8 11V7a4 4 0 0 1 7.2-2.4" />
        }
        @case ('shield') {
          <path d="M12 3l7 3v5.5c0 4.6-3 7.6-7 9-4-1.4-7-4.4-7-9V6l7-3z" />
        }
        @case ('calendar') {
          <rect x="3.5" y="5" width="17" height="16" rx="2" />
          <path d="M3.5 10h17" />
          <path d="M8 3v4" />
          <path d="M16 3v4" />
        }
        @case ('building') {
          <path d="M4 21V9l8-5 8 5v12" />
          <path d="M4 21h16" />
          <path d="M9 21v-6h6v6" />
        }
        @case ('globe') {
          <circle cx="12" cy="12" r="9" />
          <path d="M3 12h18" />
          <path d="M12 3c2.5 2.5 3.5 5.5 3.5 9s-1 6.5-3.5 9c-2.5-2.5-3.5-5.5-3.5-9s1-6.5 3.5-9z" />
        }
        @case ('contactless') {
          <path d="M8 8a8 8 0 0 1 0 8" />
          <path d="M11.5 5a12 12 0 0 1 0 14" />
          <path d="M4.5 11a4 4 0 0 1 0 2" />
        }
        @case ('phone') {
          <rect x="7" y="2" width="10" height="20" rx="2" />
          <path d="M11 18h2" />
        }
        @case ('arrow-up-right') {
          <path d="M7 17L17 7" />
          <path d="M8 7h9v9" />
        }
        @case ('arrow-down-right') {
          <path d="M7 7l10 10" />
          <path d="M17 8v9H8" />
        }
        @case ('wallet') {
          <path d="M3 7a2 2 0 0 1 2-2h13a1 1 0 0 1 1 1v3" />
          <rect x="3" y="7" width="18" height="13" rx="2" />
          <circle cx="16.5" cy="13.5" r="1.3" fill="currentColor" stroke="none" />
        }
        @case ('info') {
          <circle cx="12" cy="12" r="9" />
          <path d="M12 11v5.5" />
          <circle cx="12" cy="8" r="0.3" fill="currentColor" />
        }
        @case ('sparkles') {
          <path d="M12 4l1.2 3.4L16.5 8.6l-3.3 1.2L12 13l-1.2-3.2-3.3-1.2 3.3-1.2L12 4z" />
          <path d="M18.5 14l.7 1.9 1.9.7-1.9.7-.7 1.9-.7-1.9-1.9-.7 1.9-.7z" />
        }
        @case ('receipt') {
          <path d="M6 3h12v18l-2.5-1.5L13 21l-2.5-1.5L8 21l-2-1.5V3z" />
          <path d="M9 8h6" />
          <path d="M9 12h6" />
        }
        @case ('sun') {
          <circle cx="12" cy="12" r="4.5" />
          <path d="M12 2.5v2.5M12 19v2.5M4.6 4.6l1.8 1.8M17.6 17.6l1.8 1.8M2.5 12h2.5M19 12h2.5M4.6 19.4l1.8-1.8M17.6 6.4l1.8-1.8" />
        }
        @case ('moon') {
          <path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5z" />
        }
      }
    </svg>
  `,
})
export class Icon {
  readonly name = input.required<string>();
  readonly size = input(20);
  readonly strokeWidth = input(1.8);
}
