import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../core/api-config';

export type LoanTermMonths = 12 | 24 | 36 | 60;
// "pending_review" — cerere depusă, în așteptarea deciziei personalului.
// "rejected" — respinsă de personal, cu motiv (vezi rejection_reason).
// Banii se acordă STRICT la aprobare — vezi loans-service/app/service.py.
export type LoanStatus = 'pending_review' | 'active' | 'rejected' | 'paid_off';

export type LoanPurpose =
  | 'personal_needs'
  | 'home_renovation'
  | 'purchase_goods'
  | 'debt_refinancing'
  | 'education'
  | 'medical'
  | 'vacation'
  | 'other';
export type EmploymentStatus = 'employed_permanent' | 'employed_fixed_term' | 'self_employed' | 'retired' | 'student' | 'unemployed';
export type EmploymentTenure = 'under_6_months' | '6_to_12_months' | '1_to_3_years' | '3_to_5_years' | 'over_5_years';

/** Chestionarul de cerere credit — vezi loans-service/app/models.py::
 * LoanApplicationDetails, sursa reală de adevăr pentru forma exactă. */
export interface LoanApplicationDetails {
  purpose: LoanPurpose;
  employment_status: EmploymentStatus;
  income_source: string;
  employment_tenure: EmploymentTenure;
  declared_monthly_income_minor: number;
  has_other_debts: boolean;
  other_debts_monthly_minor: number | null;
  dependents_count: number;
  consent_credit_check: boolean;
}

export interface LoanRateView {
  term_months: LoanTermMonths;
  rate_percent_annual: number;
}

export interface LoanView {
  id: string;
  principal_minor: number;
  outstanding_principal_minor: number;
  term_months: LoanTermMonths;
  rate_percent_annual: number;
  monthly_installment_minor: number;
  payments_made: number;
  applied_at: string;
  opened_at: string | null;
  next_payment_due_at: string | null;
  status: LoanStatus;
  paid_off_at: string | null;
  rejection_reason: string | null;
  application: LoanApplicationDetails;
}

export interface LoanPaymentView {
  id: string;
  loan_id: string;
  paid_at: string;
  amount_minor: number;
  interest_portion_minor: number;
  principal_portion_minor: number;
  outstanding_after_minor: number;
}

/**
 * loans-service — credite personale, execuție reală prin accounts-service.
 * Dobânda anuală e o politică proprie MaestroBank (ca la Depozite, vezi
 * backend/services/loans-service/app/rates.py) — rata lunară se calculează
 * cu formula standard de amortizare.
 *
 * Fluxul e în DOUĂ etape, ca la o bancă reală: `apply` depune o cerere
 * ("pending_review"), FĂRĂ să acorde bani — un ofițer de credit (personal,
 * vezi /admin/loan-applications) o revizuiește și decide. Rata se plătește
 * AUTOMAT lunar, DOAR pentru un credit activ; plata anticipată (`payoff`)
 * achită doar restul de principal.
 */
@Injectable({ providedIn: 'root' })
export class LoansService {
  constructor(private readonly http: HttpClient) {}

  getRates(): Observable<LoanRateView[]> {
    return this.http.get<LoanRateView[]>(`${API_BASE_URL}/loans/rates`);
  }

  listMine(): Observable<LoanView[]> {
    return this.http.get<LoanView[]>(`${API_BASE_URL}/loans`);
  }

  apply(amountMinor: number, termMonths: LoanTermMonths, application: LoanApplicationDetails): Observable<LoanView> {
    return this.http.post<LoanView>(`${API_BASE_URL}/loans/apply`, {
      amount_minor: amountMinor,
      term_months: termMonths,
      application,
    });
  }

  getPayments(loanId: string): Observable<LoanPaymentView[]> {
    return this.http.get<LoanPaymentView[]>(`${API_BASE_URL}/loans/${loanId}/payments`);
  }

  payoff(loanId: string): Observable<LoanView> {
    return this.http.post<LoanView>(`${API_BASE_URL}/loans/${loanId}/payoff`, {});
  }
}
