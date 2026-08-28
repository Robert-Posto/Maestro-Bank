import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../core/api-config';

export interface BalanceView {
  balance: number;
}

export interface LedgerEntryView {
  id: string;
  entry_type: 'earn' | 'redeem' | 'wager' | 'wheel_win' | 'welcome_bonus';
  points_delta: number;
  created_at: string;
  category: string | null;
  reward_id: string | null;
  spin_id: string | null;
  ron_credited_minor: number | null;
}

export interface EarnRateView {
  category: string;
  rate_percent: number;
}

export interface RewardView {
  id: string;
  title: string;
  description: string;
  cost_points: number;
  reward_value_minor: number;
  affordable: boolean;
}

export interface RedeemRewardResultView {
  new_balance: number;
  ron_credited_minor: number;
  account_id: string;
}

export interface WheelSegmentView {
  id: string;
  label: string;
  reward_value_minor: number | null;
}

export interface WheelSpinResultView {
  winning_segment_id: string;
  winning_label: string;
  new_balance: number;
  ron_credited_minor: number | null;
  spin_id: string;
}

export interface WelcomeBonusStatusView {
  claimed: boolean;
  bonus_points: number;
}

export interface ClaimWelcomeBonusResultView {
  new_balance: number;
  points_awarded: number;
}

/**
 * points-service — puncte de loialitate, câștigate ca procent din
 * plățile către comercianți (NU din transferuri între useri MaestroBank —
 * vezi backend/services/points-service/app/earn_rates.py). Punctele se
 * răscumpără dintr-un catalog fix de recompense (cashback REAL, nu
 * simulat) sau se pariază la roata norocului — vezi
 * backend/services/points-service/app/{rewards_catalog,wheel_segments}.py.
 * Rezultatul unei învârtiri e decis integral pe server, ÎNAINTE de
 * răspuns — frontend-ul doar animă roata să se oprească pe segmentul deja
 * decis (vezi `spin()`, folosit în features/points/points.ts).
 */
@Injectable({ providedIn: 'root' })
export class PointsService {
  constructor(private readonly http: HttpClient) {}

  getBalance(): Observable<BalanceView> {
    return this.http.get<BalanceView>(`${API_BASE_URL}/points/balance`);
  }

  getHistory(limit = 50): Observable<LedgerEntryView[]> {
    return this.http.get<LedgerEntryView[]>(`${API_BASE_URL}/points/history`, { params: { limit } });
  }

  getEarnRates(): Observable<EarnRateView[]> {
    return this.http.get<EarnRateView[]>(`${API_BASE_URL}/points/earn-rates`);
  }

  getRewards(): Observable<RewardView[]> {
    return this.http.get<RewardView[]>(`${API_BASE_URL}/points/rewards`);
  }

  redeemReward(rewardId: string): Observable<RedeemRewardResultView> {
    return this.http.post<RedeemRewardResultView>(`${API_BASE_URL}/points/rewards/${rewardId}/redeem`, {});
  }

  getWheelSegments(): Observable<WheelSegmentView[]> {
    return this.http.get<WheelSegmentView[]>(`${API_BASE_URL}/points/wheel/segments`);
  }

  spin(wageredPoints: number): Observable<WheelSpinResultView> {
    return this.http.post<WheelSpinResultView>(`${API_BASE_URL}/points/wheel/spin`, { wagered_points: wageredPoints });
  }

  getWelcomeBonusStatus(): Observable<WelcomeBonusStatusView> {
    return this.http.get<WelcomeBonusStatusView>(`${API_BASE_URL}/points/welcome-bonus/status`);
  }

  claimWelcomeBonus(): Observable<ClaimWelcomeBonusResultView> {
    return this.http.post<ClaimWelcomeBonusResultView>(`${API_BASE_URL}/points/welcome-bonus/claim`, {});
  }
}
