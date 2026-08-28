import { Component, DestroyRef, inject, signal } from '@angular/core';
import { NavigationCancel, NavigationEnd, NavigationError, NavigationStart, Router } from '@angular/router';

import { LanguageService } from '../../../services/language.service';

/**
 * Cât durează o navigare înainte s-o considerăm „lentă" și să merite un
 * indicator. Sub pragul ăsta tranziția se simte instantanee, iar un logo
 * apărut și dispărut ar fi doar zgomot vizual.
 */
const SLOW_NAVIGATION_THRESHOLD_MS = 400;

/**
 * Cât stă pe ecran, garantat, la momentele „de brand" (intrarea în cont,
 * reîncărcarea paginii) — destul cât să se vadă o pulsație completă.
 */
const MIN_VISIBLE_BRANDED_MS = 700;

/**
 * Minimul la navigările lente: doar cât să nu clipească. Aici loader-ul
 * apare pentru că userul deja așteaptă, deci nu mai adăugăm și noi timp
 * peste o navigare care oricum a durat.
 */
const MIN_VISIBLE_SLOW_MS = 400;

/** Trebuie să rămână sincronizat cu `transition: opacity` din CSS. */
const FADE_OUT_MS = 240;

/**
 * Overlay de loading cu logo-ul MaestroBank pulsând. Montat o singură dată,
 * la rădăcină (vezi app.ts), deci vede toate navigările aplicației.
 *
 * NU apare la orice schimbare de pagină — ar obosi la o aplicație în care
 * te muți des între ecrane. Apare doar în trei situații:
 *
 *   1. La reîncărcarea paginii (F5) sau la prima deschidere — cât timp
 *      Angular pornește și rezolvă ruta inițială.
 *   2. La intrarea în cont — orice trecere din zona publică (login,
 *      register, onboarding) în /app/*, indiferent dacă s-a intrat cu
 *      parolă, cu passkey sau la finalul onboarding-ului.
 *   3. La o navigare obișnuită care depășește SLOW_NAVIGATION_THRESHOLD_MS
 *      — adică exact atunci când userul chiar ar începe să se întrebe dacă
 *      s-a blocat ceva. Navigările rapide nu arată nimic.
 */
@Component({
  selector: 'app-route-loader',
  standalone: true,
  template: `
    @if (rendered()) {
      <div
        class="route-loader"
        [class.route-loader--visible]="visible()"
        role="status"
        [attr.aria-label]="language.t('common.loading')"
      >
        <span class="route-loader__halo"></span>
        <div class="route-loader__tile">
          <img class="route-loader__logo" src="logo-mb.png" alt="" width="360" height="297" />
        </div>
      </div>
    }
  `,
  styles: [
    `
      .route-loader {
        position: fixed;
        inset: 0;
        z-index: 900;
        display: grid;
        place-items: center;
        background: var(--mb-bg);
        opacity: 0;
        pointer-events: none;
        transition: opacity 240ms ease;
      }

      .route-loader--visible {
        opacity: 1;
        pointer-events: all;
      }

      /* Halo difuz în spatele logo-ului — respiră puțin mai lent decât
         plăcuța, ca pulsația să pară vie, nu mecanică. */
      .route-loader__halo {
        grid-area: 1 / 1;
        width: 260px;
        height: 260px;
        border-radius: 50%;
        background: radial-gradient(circle, var(--mb-blue-500) 0%, transparent 68%);
        opacity: 0.28;
        animation: route-loader-halo 1600ms ease-in-out infinite;
      }

      /* Logo-ul stă pe o plăcuță deschisă, ca o iconiță de aplicație.
         Motivul e de contrast, nu decorativ: partea navy a logo-ului
         (#0d1930) e practic invizibilă pe fundalul temei dark (#0b0f1a),
         așa că fără plăcuță s-ar vedea doar bifa albastră, ca un logo rupt.
         Tokenul --mb-text-on-navy e singurul token deschis care NU se
         redefinește în tema dark (vezi styles.css) — exact ce ne trebuie ca
         plăcuța să rămână deschisă în ambele teme, la fel cum sidebar-ul
         rămâne navy indiferent de temă. */
      .route-loader__tile {
        grid-area: 1 / 1;
        display: grid;
        place-items: center;
        width: 148px;
        height: 148px;
        border-radius: 34px;
        background: var(--mb-text-on-navy);
        box-shadow: var(--mb-shadow-lg);
        animation: route-loader-pulse 800ms ease-in-out infinite;
      }

      .route-loader__logo {
        width: 92px;
        height: auto;
      }

      @keyframes route-loader-pulse {
        0%,
        100% {
          transform: scale(0.9);
          opacity: 0.78;
        }
        50% {
          transform: scale(1.06);
          opacity: 1;
        }
      }

      @keyframes route-loader-halo {
        0%,
        100% {
          transform: scale(0.82);
          opacity: 0.2;
        }
        50% {
          transform: scale(1.18);
          opacity: 0.4;
        }
      }

      @media (prefers-reduced-motion: reduce) {
        .route-loader__tile,
        .route-loader__halo {
          animation: none;
        }
      }
    `,
  ],
})
export class RouteLoader {
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly language = inject(LanguageService);

  /** Prezent în DOM — rămâne `true` și pe durata fade-out-ului. */
  protected readonly rendered = signal(false);
  /** Controlează opacitatea. Separat de `rendered`, ca tranziția CSS să
   * aibă o stare de plecare (opacity: 0) de la care să pornească. */
  protected readonly visible = signal(false);

  private slowTimer?: ReturnType<typeof setTimeout>;
  private hideTimer?: ReturnType<typeof setTimeout>;
  private removeTimer?: ReturnType<typeof setTimeout>;
  private shownAt = 0;
  private minVisibleMs = MIN_VISIBLE_BRANDED_MS;

  constructor() {
    const subscription = this.router.events.subscribe((event) => {
      if (event instanceof NavigationStart) {
        this.onNavigationStart(event.url);
      } else if (
        event instanceof NavigationEnd ||
        event instanceof NavigationCancel ||
        event instanceof NavigationError
      ) {
        clearTimeout(this.slowTimer);
        this.hideAfterMinimum();
      }
    });

    // Cazul „refresh / prima deschidere". Componenta se construiește o
    // singură dată per încărcare de pagină, deci simplul fapt că suntem
    // aici înseamnă că pagina tocmai s-a (re)încărcat.
    this.show(MIN_VISIBLE_BRANDED_MS);
    if (this.router.navigated) {
      // Navigarea inițială s-a încheiat deja înainte ca această componentă
      // să existe (Angular o poate rezolva în timpul bootstrap-ului), deci
      // nu va mai veni niciun NavigationEnd care s-o ascundă — o programăm
      // noi acum, altfel overlay-ul ar rămâne blocat pe ecran.
      this.hideAfterMinimum();
    }

    this.destroyRef.onDestroy(() => {
      subscription.unsubscribe();
      clearTimeout(this.slowTimer);
      clearTimeout(this.hideTimer);
      clearTimeout(this.removeTimer);
    });
  }

  private onNavigationStart(targetUrl: string): void {
    if (this.isEnteringApp(targetUrl)) {
      this.show(MIN_VISIBLE_BRANDED_MS);
      return;
    }
    // Navigare obișnuită: nu arătăm nimic deocamdată. Dacă trece pragul,
    // înseamnă că userul chiar așteaptă — abia atunci apare loader-ul.
    clearTimeout(this.slowTimer);
    this.slowTimer = setTimeout(() => this.show(MIN_VISIBLE_SLOW_MS), SLOW_NAVIGATION_THRESHOLD_MS);
  }

  /**
   * Trecere din zona publică (login/register/onboarding) în aplicație —
   * adică userul tocmai a intrat în cont. `router.url` e încă ruta veche
   * în momentul NavigationStart, de-aia comparația funcționează.
   */
  private isEnteringApp(targetUrl: string): boolean {
    return targetUrl.startsWith('/app') && !this.router.url.startsWith('/app');
  }

  private show(minVisibleMs: number): void {
    clearTimeout(this.hideTimer);
    clearTimeout(this.removeTimer);

    // Deja complet afișat (ex. un guard redirecționează imediat spre altă
    // rută) — îl lăsăm cum e, fără să repornim cronometrul minim; altfel
    // un lanț de redirect-uri ar ține loader-ul pe ecran la nesfârșit.
    if (this.visible()) return;

    this.minVisibleMs = minVisibleMs;
    this.rendered.set(true);
    this.shownAt = Date.now();
    // Un frame în care elementul există cu opacity: 0, ca tranziția să
    // aibă de unde porni (altfel apare brusc, fără fade).
    requestAnimationFrame(() => this.visible.set(true));
  }

  private hideAfterMinimum(): void {
    if (!this.rendered()) return;

    const remaining = Math.max(0, this.minVisibleMs - (Date.now() - this.shownAt));
    clearTimeout(this.hideTimer);
    this.hideTimer = setTimeout(() => {
      this.visible.set(false);
      this.removeTimer = setTimeout(() => this.rendered.set(false), FADE_OUT_MS);
    }, remaining);
  }
}
