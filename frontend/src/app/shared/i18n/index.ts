import { COMMON_I18N } from './common.i18n';
import { AUTH_I18N } from './auth.i18n';
import { NAV_I18N } from './nav.i18n';
import { OVERVIEW_I18N } from './overview.i18n';
import { ACCOUNTS_I18N } from './accounts.i18n';
import { CARDS_I18N } from './cards.i18n';
import { TRANSACTIONS_I18N } from './transactions.i18n';
import { TRANSFERS_I18N } from './transfers.i18n';
import { EXCHANGE_I18N } from './exchange.i18n';
import { INVESTMENTS_I18N } from './investments.i18n';
import { BUDGETS_I18N } from './budgets.i18n';
import { DEPOSITS_I18N } from './deposits.i18n';
import { FORECAST_I18N } from './forecast.i18n';
import { SUPPORT_I18N } from './support.i18n';
import { COPILOT_I18N } from './copilot.i18n';
import { PROFILE_I18N } from './profile.i18n';
import { PAY_REQUEST_I18N } from './pay-request.i18n';
import { STAFF_I18N } from './staff.i18n';
import { LOANS_I18N } from './loans.i18n';
import { POINTS_I18N } from './points.i18n';

export interface TranslationEntry {
  ro: string;
  en: string;
}

/** Dicționar unic RO/EN, agregat din fișierele pe domeniu de mai jos —
 * fiecare cheie ține ambele limbi co-locate, ca să nu poată diverge (vezi
 * planul fazei). Populat progresiv, pagină cu pagină. */
export const TRANSLATIONS: Record<string, TranslationEntry> = {
  ...COMMON_I18N,
  ...AUTH_I18N,
  ...NAV_I18N,
  ...OVERVIEW_I18N,
  ...ACCOUNTS_I18N,
  ...CARDS_I18N,
  ...TRANSACTIONS_I18N,
  ...TRANSFERS_I18N,
  ...EXCHANGE_I18N,
  ...INVESTMENTS_I18N,
  ...BUDGETS_I18N,
  ...DEPOSITS_I18N,
  ...FORECAST_I18N,
  ...SUPPORT_I18N,
  ...COPILOT_I18N,
  ...PROFILE_I18N,
  ...PAY_REQUEST_I18N,
  ...STAFF_I18N,
  ...LOANS_I18N,
  ...POINTS_I18N,
};
