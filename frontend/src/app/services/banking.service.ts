import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../core/api-config';
import { WebauthnStepUpProof } from './webauthn.service';

/** "current" e provizionat automat la înregistrare — celelalte 3 se deschid manual, vezi CreatableAccountType. */
export type AccountType = 'current' | 'savings' | 'deposit' | 'student';
export type CreatableAccountType = 'savings' | 'deposit' | 'student';

export interface AccountView {
  id: string;
  iban: string;
  currency: string;
  balance_minor: number;
  balance: string;
  status: string;
  created_at: string;
  account_type: AccountType;
  /** Numele fișierului atașat la deschidere (ex. cont student) — metadata, nu conținutul fișierului. */
  verification_document_name: string | null;
}

export type CardDesign = 'midnight' | 'aurora' | 'rose-gold' | 'graphite' | 'arctic';
export type CardType = 'virtual' | 'physical';

export interface CardView {
  id: string;
  user_id: string;
  account_id: string;
  last_four: string;
  expiry_month: number;
  expiry_year: number;
  status: string;
  type: CardType;
  created_at: string;
  is_frozen: boolean;
  online_payments_enabled: boolean;
  contactless_enabled: boolean;
  atm_withdrawals_enabled: boolean;
  international_payments_enabled: boolean;
  daily_limit_minor: number;
  design: CardDesign;
  is_one_time: boolean;
}

export interface CardSettingsPayload {
  online_payments_enabled?: boolean;
  contactless_enabled?: boolean;
  atm_withdrawals_enabled?: boolean;
  international_payments_enabled?: boolean;
}

export interface CardCreatePayload {
  design: CardDesign;
  type: CardType;
  is_one_time: boolean;
}

export interface CardRevealView {
  pan: string;
  cvv: string;
  expiry_month: number;
  expiry_year: number;
}

/** Taxă de emitere card fizic — vezi accounts-service::_PHYSICAL_CARD_FEE_MINOR. */
export const PHYSICAL_CARD_FEE_MINOR = 2_000;

export interface PocketView {
  id: string;
  name: string;
  target_minor: number;
  saved_minor: number;
  created_at: string;
}

export interface Beneficiary {
  id: string;
  name: string;
  iban: string;
  created_at: string;
}

export interface HoldInfo {
  expires_at: string;
  /** null cât timp reținerea e activă — vezi app/holds.py din backend. */
  resolution: string | null;
}

/** Evaluarea de risc Financial Guardian, orientată client — vezi
 * app/guardian/ din backend. `phrase` e null cât timp `status` e "pending"
 * (fraza pentru "unusual"/"potentially_dangerous" se generează asincron,
 * la scurt timp după creare) — "safe"/"held" au mereu status "ready",
 * frază fixă, calculate sincron. NU conține NICIODATĂ ID-uri de regulă. */
export interface TransactionRisk {
  tier: 'safe' | 'unusual' | 'potentially_dangerous' | 'held';
  phrase: string | null;
  status: 'pending' | 'ready' | 'template_fallback';
}

export interface TransactionView {
  id: string;
  direction: 'incoming' | 'outgoing';
  amount_minor: number;
  amount: string;
  currency: string;
  counterparty_iban: string;
  /** "Prenume Nume", doar pentru transferuri către/de la un user MaestroBank real — null pentru comercianți. */
  counterparty_name: string | null;
  description: string;
  category: string;
  status: string;
  recognized: boolean;
  reported: boolean;
  created_at: string;
  /** Prezent DOAR pe tranzacții care AU FOST reținute de motorul de fraud (status="pending_review") — vezi app/holds.py. */
  hold: HoldInfo | null;
  /** null DOAR pentru tranzacții dinainte de Financial Guardian sau când motorul e dezactivat — vezi app/guardian/. */
  risk: TransactionRisk | null;
}

export interface TransferPayload {
  to_iban: string;
  amount_minor: number;
  description: string;
  category?: string;
}

export type ScheduleFrequency = 'weekly' | 'monthly';

export interface ScheduledTransferView {
  id: string;
  to_iban: string;
  amount_minor: number;
  description: string;
  frequency: ScheduleFrequency;
  next_run_at: string;
  active: boolean;
  created_at: string;
}

export interface ScheduledTransferPayload {
  to_iban: string;
  amount_minor: number;
  description: string;
  frequency: ScheduleFrequency;
}

@Injectable({ providedIn: 'root' })
export class BankingService {
  constructor(private readonly http: HttpClient) {}

  getMyAccount(): Observable<AccountView> {
    return this.http.get<AccountView>(`${API_BASE_URL}/accounts/me`);
  }

  /** Toate conturile userului: curent + economii/depozit/student (dacă au fost deschise). */
  getAllAccounts(): Observable<AccountView[]> {
    return this.http.get<AccountView[]>(`${API_BASE_URL}/accounts/all`);
  }

  /**
   * Deschide un cont suplimentar. Un singur cont per tip — vezi
   * accounts-service::create_additional_account. `documentFilename` e
   * obligatoriu pentru "student" (doar numele fișierului — nu încărcăm
   * conținutul, vezi nota din accounts-service/app/models.py).
   */
  createAccount(accountType: CreatableAccountType, documentFilename?: string | null): Observable<AccountView> {
    return this.http.post<AccountView>(`${API_BASE_URL}/accounts/new`, {
      account_type: accountType,
      document_filename: documentFilename ?? null,
    });
  }

  /** Închide un cont suplimentar — contul curent nu poate fi șters, contul trebuie golit întâi. */
  deleteAccount(accountId: string): Observable<void> {
    return this.http.delete<void>(`${API_BASE_URL}/accounts/${accountId}`);
  }

  getMyCards(): Observable<CardView[]> {
    return this.http.get<CardView[]>(`${API_BASE_URL}/accounts/me/cards`);
  }

  /** ⚠️ STRICT development-only — vezi backend accounts-service POST /accounts/dev/fund. */
  devFund(amountMinor: number): Observable<AccountView> {
    return this.http.post<AccountView>(`${API_BASE_URL}/accounts/dev/fund`, { amount_minor: amountMinor });
  }

  createTransfer(payload: TransferPayload): Observable<TransactionView> {
    return this.http.post<TransactionView>(`${API_BASE_URL}/transactions/transfers`, payload);
  }

  getTransactions(limit = 20, skip = 0): Observable<TransactionView[]> {
    return this.http.get<TransactionView[]>(`${API_BASE_URL}/transactions?limit=${limit}&skip=${skip}`);
  }

  // --- Card controls (Cardul meu) — vezi accounts-service /cards/{id}/* ---

  createCard(payload: CardCreatePayload): Observable<CardView> {
    return this.http.post<CardView>(`${API_BASE_URL}/accounts/cards`, payload);
  }

  /** `proof` e fie o parolă, fie un assertion WebAuthn (vezi
   * WebauthnService.getStepUpAssertion) — accounts-service acceptă exact
   * una dintre cele două metode, nu ambele. */
  revealCard(cardId: string, proof: { password: string } | WebauthnStepUpProof): Observable<CardRevealView> {
    return this.http.post<CardRevealView>(`${API_BASE_URL}/accounts/cards/${cardId}/reveal`, proof);
  }

  freezeCard(cardId: string): Observable<CardView> {
    return this.http.patch<CardView>(`${API_BASE_URL}/accounts/cards/${cardId}/freeze`, {});
  }

  unfreezeCard(cardId: string): Observable<CardView> {
    return this.http.patch<CardView>(`${API_BASE_URL}/accounts/cards/${cardId}/unfreeze`, {});
  }

  updateCardSettings(cardId: string, payload: CardSettingsPayload): Observable<CardView> {
    return this.http.patch<CardView>(`${API_BASE_URL}/accounts/cards/${cardId}/settings`, payload);
  }

  updateCardLimit(cardId: string, dailyLimitMinor: number): Observable<CardView> {
    return this.http.patch<CardView>(`${API_BASE_URL}/accounts/cards/${cardId}/limits`, {
      daily_limit_minor: dailyLimitMinor,
    });
  }

  // --- Beneficiari (transfer rapid) ---------------------------------------

  getBeneficiaries(): Observable<Beneficiary[]> {
    return this.http.get<Beneficiary[]>(`${API_BASE_URL}/accounts/beneficiaries`);
  }

  createBeneficiary(name: string, iban: string): Observable<Beneficiary> {
    return this.http.post<Beneficiary>(`${API_BASE_URL}/accounts/beneficiaries`, { name, iban });
  }

  deleteBeneficiary(id: string): Observable<void> {
    return this.http.delete<void>(`${API_BASE_URL}/accounts/beneficiaries/${id}`);
  }

  // --- Pockets (obiective de economisire) ---------------------------------

  getPockets(): Observable<PocketView[]> {
    return this.http.get<PocketView[]>(`${API_BASE_URL}/accounts/pockets`);
  }

  createPocket(name: string, targetMinor: number): Observable<PocketView> {
    return this.http.post<PocketView>(`${API_BASE_URL}/accounts/pockets`, { name, target_minor: targetMinor });
  }

  depositToPocket(pocketId: string, amountMinor: number): Observable<PocketView> {
    return this.http.post<PocketView>(`${API_BASE_URL}/accounts/pockets/${pocketId}/deposit`, {
      amount_minor: amountMinor,
    });
  }

  withdrawFromPocket(pocketId: string, amountMinor: number): Observable<PocketView> {
    return this.http.post<PocketView>(`${API_BASE_URL}/accounts/pockets/${pocketId}/withdraw`, {
      amount_minor: amountMinor,
    });
  }

  deletePocket(id: string): Observable<void> {
    return this.http.delete<void>(`${API_BASE_URL}/accounts/pockets/${id}`);
  }

  // --- Transferuri programate/recurente -----------------------------------

  getScheduledTransfers(): Observable<ScheduledTransferView[]> {
    return this.http.get<ScheduledTransferView[]>(`${API_BASE_URL}/transactions/scheduled-transfers`);
  }

  createScheduledTransfer(payload: ScheduledTransferPayload): Observable<ScheduledTransferView> {
    return this.http.post<ScheduledTransferView>(`${API_BASE_URL}/transactions/scheduled-transfers`, payload);
  }

  cancelScheduledTransfer(id: string): Observable<void> {
    return this.http.delete<void>(`${API_BASE_URL}/transactions/scheduled-transfers/${id}`);
  }
}
