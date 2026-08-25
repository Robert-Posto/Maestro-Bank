import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { forkJoin, of } from 'rxjs';

import {
  AccountView,
  BankingService,
  CardCreatePayload,
  CardDesign,
  CardRevealView,
  CardType,
  CardView,
  PHYSICAL_CARD_FEE_MINOR,
} from '../../services/banking.service';
import { TransactionsService, SpendingAnalytics } from '../../services/transactions.service';
import { AuthService } from '../../services/auth.service';
import { WebauthnService } from '../../services/webauthn.service';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { StatusBadge } from '../../shared/components/status-badge/status-badge';
import { ToggleControl } from '../../shared/components/toggle-control/toggle-control';
import { LoadingSkeleton } from '../../shared/components/loading-skeleton/loading-skeleton';
import { EmptyState } from '../../shared/components/empty-state/empty-state';
import { TransactionRow, TransactionRowData } from '../../shared/components/transaction-row/transaction-row';
import { ActionButton } from '../../shared/components/action-button/action-button';
import { Modal } from '../../shared/components/modal/modal';
import { MoneyPipe } from '../../shared/pipes/money.pipe';
import { Icon } from '../../shared/components/icon/icon';
import { ToastService } from '../../shared/components/toast/toast.service';
import { extractErrorMessage } from '../../shared/error-utils';

type ToggleKey = 'online_payments_enabled' | 'contactless_enabled' | 'atm_withdrawals_enabled' | 'international_payments_enabled';
type AccordionSection = 'details' | 'control' | 'security';

const REVEAL_AUTO_HIDE_MS = 20_000;

interface CardDesignOption {
  value: CardDesign;
  label: string;
  gradient: string;
  /** Design cu fundal deschis — cere text/overlay-uri închise (vezi .card-visual--light în CSS). */
  light: boolean;
}

const CARD_DESIGN_OPTIONS: CardDesignOption[] = [
  { value: 'midnight', label: 'Midnight', gradient: 'linear-gradient(135deg, var(--mb-navy-800) 0%, var(--mb-navy-950) 100%)', light: false },
  { value: 'aurora', label: 'Aurora', gradient: 'linear-gradient(135deg, #17264a 0%, #2f6fed 55%, #7c3aed 100%)', light: false },
  { value: 'rose-gold', label: 'Rose Gold', gradient: 'linear-gradient(135deg, #3a2030 0%, #a85f72 55%, #e8c39c 100%)', light: false },
  { value: 'graphite', label: 'Graphite', gradient: 'linear-gradient(135deg, #232428 0%, #46484f 100%)', light: false },
  { value: 'arctic', label: 'Arctic', gradient: 'linear-gradient(135deg, #eef4ff 0%, #d3e2fb 60%, #a9c3ef 100%)', light: true },
];

/**
 * Cardurile mele — vezi UI reference/Cards.png și task-ul MaestroBank,
 * secțiunea 9. NU generăm PAN/CVV reale — sunt generate demo, doar pentru
 * acest prototip (vezi accounts-service::_generate_demo_pan). Card controls
 * sunt reale (accounts-service), userul poate modifica DOAR propriile
 * carduri (identitate din JWT — vezi backend).
 */
@Component({
  selector: 'app-cards',
  standalone: true,
  imports: [
    PageHeader,
    StatusBadge,
    ToggleControl,
    LoadingSkeleton,
    EmptyState,
    TransactionRow,
    ActionButton,
    Modal,
    MoneyPipe,
    Icon,
    FormsModule,
  ],
  templateUrl: './cards.html',
  styleUrl: './cards.css',
})
export class Cards implements OnInit, OnDestroy {
  private readonly banking = inject(BankingService);
  private readonly transactionsApi = inject(TransactionsService);
  private readonly auth = inject(AuthService);
  private readonly webauthn = inject(WebauthnService);
  private readonly toast = inject(ToastService);

  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);

  protected readonly account = signal<AccountView | null>(null);
  protected readonly cards = signal<CardView[]>([]);
  protected readonly activeIndex = signal(0);
  protected readonly activeCard = computed<CardView | null>(() => this.cards()[this.activeIndex()] ?? null);

  protected readonly spending = signal<SpendingAnalytics | null>(null);
  protected readonly recentTransactions = signal<TransactionRowData[]>([]);

  // --- Accordion (Detalii / Control / Security) ------------------------
  // Doar o secțiune deschisă simultan — pagina asta era cea mai "densă"
  // din audit (3 secțiuni mereu întinse una sub alta).
  protected readonly openSection = signal<AccordionSection | null>('details');

  protected toggleSection(section: AccordionSection): void {
    this.openSection.update((current) => (current === section ? null : section));
  }

  protected readonly freezeBusy = signal(false);
  protected readonly settingsBusy = signal<ToggleKey | null>(null);
  protected readonly limitBusy = signal(false);
  protected readonly limitInput = signal(0);
  protected readonly editingLimit = signal(false);

  protected readonly cardholderName = computed(() => {
    const user = this.auth.currentUser();
    return user ? `${user.first_name} ${user.last_name}`.toUpperCase() : '';
  });

  // --- Emitere card nou -----------------------------------------------
  protected readonly cardDesignOptions = CARD_DESIGN_OPTIONS;
  protected readonly physicalCardFeeMinor = PHYSICAL_CARD_FEE_MINOR;

  protected readonly addCardModalOpen = signal(false);
  protected readonly addCardSaving = signal(false);
  protected readonly addCardDesign = signal<CardDesign>('midnight');
  protected readonly addCardType = signal<CardType>('virtual');
  protected readonly addCardOneTime = signal(false);
  /** PIN-ul ALES de user chiar la deschiderea cardului (ca la un card real
   * fizic emis de bancă) — folosit ulterior la reveal (vezi mai jos, secțiunea
   * "Vezi date card + CVV"), NU parola contului. */
  protected readonly addCardPin = signal('');
  protected readonly addCardPinConfirm = signal('');

  protected readonly physicalFeeShortfall = computed(
    () => this.addCardType() === 'physical' && (this.account()?.balance_minor ?? 0) < PHYSICAL_CARD_FEE_MINOR,
  );

  // --- Vezi date card + CVV (passkey, cu fallback pe PIN-ul cardului) --
  protected readonly revealModalOpen = signal(false);
  protected readonly revealPin = signal('');
  protected readonly revealBusy = signal(false);
  protected readonly revealBiometricBusy = signal(false);
  protected readonly revealTarget = signal<CardView | null>(null);
  protected readonly revealedCardId = signal<string | null>(null);
  protected readonly revealedData = signal<CardRevealView | null>(null);
  private autoHideTimer?: ReturnType<typeof setTimeout>;

  private readonly hasPasskey = signal(false);
  protected readonly passkeyAvailable = computed(() => this.webauthn.isSupported() && this.hasPasskey());

  ngOnInit(): void {
    this.load();
  }

  ngOnDestroy(): void {
    this.clearAutoHideTimer();
  }

  private load(): void {
    this.loading.set(true);
    this.error.set(null);

    forkJoin({
      account: this.banking.getMyAccount(),
      cards: this.banking.getMyCards(),
      spending: this.transactionsApi.getSpendingAnalytics(),
      transactions: this.banking.getTransactions(4, 0),
      // Doar dacă browserul suportă WebAuthn — evită un apel de rețea inutil
      // pe unul care nu-l suportă oricum (vezi passkeyAvailable).
      passkeys: this.webauthn.isSupported() ? this.webauthn.listCredentials() : of([]),
    }).subscribe({
      next: ({ account, cards, spending, transactions, passkeys }) => {
        this.account.set(account);
        this.cards.set(cards);
        this.activeIndex.set(0);
        this.spending.set(spending);
        this.recentTransactions.set(transactions);
        this.hasPasskey.set(passkeys.length > 0);
        this.loading.set(false);
      },
      error: () => {
        this.error.set('Nu am putut încărca datele cardului.');
        this.loading.set(false);
      },
    });
  }

  private replaceCard(updated: CardView): void {
    this.cards.update((list) => list.map((c) => (c.id === updated.id ? updated : c)));
  }

  private onActiveCardChanged(): void {
    this.editingLimit.set(false);
    this.hideReveal();
  }

  // --- Carusel carduri --------------------------------------------------

  protected prevCard(): void {
    const total = this.cards().length;
    if (total <= 1) return;
    this.activeIndex.update((i) => (i - 1 + total) % total);
    this.onActiveCardChanged();
  }

  protected nextCard(): void {
    const total = this.cards().length;
    if (total <= 1) return;
    this.activeIndex.update((i) => (i + 1) % total);
    this.onActiveCardChanged();
  }

  protected goToCard(index: number): void {
    if (index === this.activeIndex()) return;
    this.activeIndex.set(index);
    this.onActiveCardChanged();
  }

  // --- Control card (freeze/settings/limit) -----------------------------

  protected toggleFreeze(): void {
    const current = this.activeCard();
    if (!current) return;

    this.freezeBusy.set(true);
    const request = current.is_frozen ? this.banking.unfreezeCard(current.id) : this.banking.freezeCard(current.id);
    request.subscribe({
      next: (updated) => {
        this.replaceCard(updated);
        this.freezeBusy.set(false);
        this.toast.success(updated.is_frozen ? 'Card blocat temporar.' : 'Card deblocat.');
      },
      error: (err) => {
        this.freezeBusy.set(false);
        this.toast.error(extractErrorMessage(err, 'Nu am putut actualiza statusul cardului.'));
      },
    });
  }

  protected toggleSetting(key: ToggleKey, value: boolean): void {
    const current = this.activeCard();
    if (!current) return;

    this.settingsBusy.set(key);
    this.banking.updateCardSettings(current.id, { [key]: value }).subscribe({
      next: (updated) => {
        this.replaceCard(updated);
        this.settingsBusy.set(null);
        this.toast.success('Setările cardului au fost actualizate.');
      },
      error: (err) => {
        this.settingsBusy.set(null);
        this.toast.error(extractErrorMessage(err, 'Nu am putut actualiza setarea.'));
      },
    });
  }

  protected openLimitEditor(): void {
    const current = this.activeCard();
    if (!current) return;
    this.limitInput.set(current.daily_limit_minor / 100);
    this.editingLimit.set(true);
  }

  protected saveLimit(): void {
    const current = this.activeCard();
    if (!current) return;
    const minor = Math.round(this.limitInput() * 100);
    if (minor <= 0) {
      this.toast.error('Introdu o limită validă.');
      return;
    }

    this.limitBusy.set(true);
    this.banking.updateCardLimit(current.id, minor).subscribe({
      next: (updated) => {
        this.replaceCard(updated);
        this.limitBusy.set(false);
        this.editingLimit.set(false);
        this.toast.success('Limita zilnică a fost actualizată.');
      },
      error: (err) => {
        this.limitBusy.set(false);
        this.toast.error(extractErrorMessage(err, 'Nu am putut actualiza limita.'));
      },
    });
  }

  // --- Emitere card nou ---------------------------------------------------

  protected openAddCardModal(): void {
    this.addCardDesign.set('midnight');
    this.addCardType.set('virtual');
    this.addCardOneTime.set(false);
    this.addCardPin.set('');
    this.addCardPinConfirm.set('');
    this.addCardModalOpen.set(true);
  }

  protected selectCardType(type: CardType): void {
    this.addCardType.set(type);
    if (type === 'physical') {
      this.addCardOneTime.set(false);
    }
  }

  protected toggleOneTime(value: boolean): void {
    this.addCardOneTime.set(value);
    if (value) {
      this.addCardType.set('virtual');
    }
  }

  protected saveNewCard(): void {
    if (this.physicalFeeShortfall()) {
      this.toast.error('Sold insuficient pentru taxa de emitere a cardului fizic.');
      return;
    }
    if (!/^\d{4}$/.test(this.addCardPin())) {
      this.toast.error('PIN-ul trebuie să conțină exact 4 cifre.');
      return;
    }
    if (this.addCardPin() !== this.addCardPinConfirm()) {
      this.toast.error('PIN-urile introduse nu coincid.');
      return;
    }

    const payload: CardCreatePayload = {
      design: this.addCardDesign(),
      type: this.addCardType(),
      is_one_time: this.addCardOneTime(),
      pin: this.addCardPin(),
    };

    this.addCardSaving.set(true);
    this.banking.createCard(payload).subscribe({
      next: (card) => {
        this.cards.update((list) => [...list, card]);
        this.activeIndex.set(this.cards().length - 1);
        this.onActiveCardChanged();
        this.addCardSaving.set(false);
        this.addCardModalOpen.set(false);
        this.toast.success(payload.type === 'physical' ? 'Card fizic comandat.' : 'Card virtual emis.');

        if (payload.type === 'physical') {
          this.banking.getMyAccount().subscribe((account) => this.account.set(account));
        }
      },
      error: (err) => {
        this.addCardSaving.set(false);
        this.toast.error(extractErrorMessage(err, 'Nu am putut emite cardul.'));
      },
    });
  }

  // --- Vezi date card + CVV (passkey, cu fallback pe parolă) --------------

  protected isRevealedCard(cardId: string): boolean {
    return this.revealedCardId() === cardId && this.revealedData() !== null;
  }

  protected onEyeClick(card: CardView): void {
    if (this.isRevealedCard(card.id)) {
      this.hideReveal();
      return;
    }
    this.revealTarget.set(card);
    this.revealPin.set('');
    this.revealModalOpen.set(true);
  }

  protected closeRevealModal(): void {
    this.revealModalOpen.set(false);
    this.revealPin.set('');
    this.revealTarget.set(null);
  }

  protected submitReveal(): void {
    const target = this.revealTarget();
    if (!target) return;
    if (!/^\d{4}$/.test(this.revealPin())) {
      this.toast.error('Introdu PIN-ul cardului (4 cifre).');
      return;
    }

    this.revealBusy.set(true);
    this.banking.revealCard(target.id, { pin: this.revealPin() }).subscribe({
      next: (data) => this.applyRevealSuccess(target.id, data, () => this.revealBusy.set(false)),
      error: (err) => {
        this.revealBusy.set(false);
        this.toast.error(extractErrorMessage(err, 'PIN incorect.'));
      },
    });
  }

  protected async submitRevealWithBiometrics(): Promise<void> {
    const target = this.revealTarget();
    if (!target) return;

    this.revealBiometricBusy.set(true);
    try {
      const proof = await this.webauthn.getStepUpAssertion('card_reveal', target.id);
      this.banking.revealCard(target.id, proof).subscribe({
        next: (data) => this.applyRevealSuccess(target.id, data, () => this.revealBiometricBusy.set(false)),
        error: (err) => {
          this.revealBiometricBusy.set(false);
          this.toast.error(extractErrorMessage(err, 'Confirmarea biometrică a eșuat — poți folosi PIN-ul.'));
        },
      });
    } catch (err) {
      this.revealBiometricBusy.set(false);
      // Userul a anulat prompt-ul biometric (NotAllowedError) — nu e o
      // eroare de afișat, câmpul PIN-ului rămâne oricum disponibil mai jos.
      if ((err as { name?: string })?.name !== 'NotAllowedError') {
        this.toast.error('Confirmarea biometrică nu a funcționat — poți folosi PIN-ul.');
      }
    }
  }

  private applyRevealSuccess(cardId: string, data: CardRevealView, clearBusy: () => void): void {
    this.revealedData.set(data);
    this.revealedCardId.set(cardId);
    clearBusy();
    this.revealModalOpen.set(false);
    this.revealPin.set('');
    this.revealTarget.set(null);
    this.scheduleAutoHide();
  }

  protected hideReveal(): void {
    this.clearAutoHideTimer();
    this.revealedData.set(null);
    this.revealedCardId.set(null);
  }

  private scheduleAutoHide(): void {
    this.clearAutoHideTimer();
    this.autoHideTimer = setTimeout(() => this.hideReveal(), REVEAL_AUTO_HIDE_MS);
  }

  private clearAutoHideTimer(): void {
    if (this.autoHideTimer) {
      clearTimeout(this.autoHideTimer);
      this.autoHideTimer = undefined;
    }
  }

  protected formatPan(pan: string): string {
    return pan.match(/.{1,4}/g)?.join(' ') ?? pan;
  }

  private designOption(design: CardDesign): CardDesignOption | undefined {
    return this.cardDesignOptions.find((d) => d.value === design);
  }

  protected designLabel(design: CardDesign): string {
    return this.designOption(design)?.label ?? design;
  }

  protected designGradient(design: CardDesign): string {
    return this.designOption(design)?.gradient ?? '';
  }

  protected isLightDesign(design: CardDesign): boolean {
    return this.designOption(design)?.light ?? false;
  }
}
