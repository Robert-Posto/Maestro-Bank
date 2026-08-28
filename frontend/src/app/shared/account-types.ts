import { AccountType, CreatableAccountType } from '../services/banking.service';
import { Language } from '../services/language.service';

/**
 * Catalog STATIC cu tipurile de cont — folosit la deschiderea unui cont nou
 * (Accounts feature) și la afișarea etichetei/culorii unui cont existent.
 * Ratele/beneficiile sunt informative (ca la orice catalog de produse
 * bancare), NU sunt simulate/acumulate automat — nu există încă un job care
 * să calculeze dobândă reală (la fel cum "Financial Guardian" e marcat
 * "Coming in AI phase" în altă parte a aplicației, nu promitem ceva ce nu
 * rulează efectiv).
 *
 * Câmpurile `label`/`tagline`/`rateLabel`/`benefits`/`documentHint` rămân
 * varianta RO (folosită de paginile care nu sunt încă traduse — Staff/Support
 * citesc direct `.label`); câmpurile `*En` sunt varianta EN, alese prin
 * funcțiile accessor de mai jos (mirror pe categories.ts::categoryLabel).
 */
export interface AccountTypeMeta {
  type: AccountType;
  label: string;
  labelEn: string;
  tagline: string;
  taglineEn: string;
  icon: string;
  colorVar: string;
  rateLabel: string;
  rateLabelEn: string;
  benefits: string[];
  benefitsEn: string[];
  /** Necesită un document justificativ înainte de deschidere (ex. student → adeverință/carnet). */
  requiresDocument?: boolean;
  documentHint?: string;
  documentHintEn?: string;
}

export const ACCOUNT_TYPE_CATALOG: Record<AccountType, AccountTypeMeta> = {
  current: {
    type: 'current',
    label: 'Cont curent',
    labelEn: 'Current account',
    tagline: 'Contul tău principal, pentru cheltuieli și transferuri zilnice.',
    taglineEn: 'Your main account, for everyday spending and transfers.',
    icon: 'wallet',
    colorVar: '--mb-blue-500',
    rateLabel: 'Fără dobândă',
    rateLabelEn: 'No interest',
    benefits: ['Card atașat, activ imediat', 'Transferuri și plăți nelimitate', 'Fără sold minim'],
    benefitsEn: ['Card attached, active immediately', 'Unlimited transfers and payments', 'No minimum balance'],
  },
  savings: {
    type: 'savings',
    label: 'Cont de economii',
    labelEn: 'Savings account',
    tagline: 'Pui bani deoparte, separat de cheltuielile zilnice, cu acces oricând.',
    taglineEn: 'Set money aside, separate from everyday spending, with access anytime.',
    icon: 'sparkles',
    colorVar: '--mb-cat-groceries',
    rateLabel: '~3,5%/an, indicativ',
    rateLabelEn: '~3.5%/year, indicative',
    benefits: ['IBAN propriu, separat de contul curent', 'Retragi oricând, fără penalizări', 'Fără card atașat'],
    benefitsEn: ['Own IBAN, separate from your current account', 'Withdraw anytime, no penalties', 'No card attached'],
  },
  deposit: {
    type: 'deposit',
    label: 'Cont de depozit',
    labelEn: 'Deposit account',
    tagline: 'Dobândă mai bună pentru bani pe care nu-i atingi o vreme.',
    taglineEn: "Better interest for money you won't touch for a while.",
    icon: 'shield',
    colorVar: '--mb-cat-bills',
    rateLabel: '~5,8%/an, indicativ',
    rateLabelEn: '~5.8%/year, indicative',
    benefits: ['Randament mai mare decât economiile', 'Ideal pentru un obiectiv pe termen mediu', 'IBAN propriu, urmărit separat'],
    benefitsEn: ['Higher yield than a savings account', 'Ideal for a medium-term goal', 'Own IBAN, tracked separately'],
  },
  student: {
    type: 'student',
    label: 'Cont student',
    labelEn: 'Student account',
    tagline: 'Gândit pentru studenți — fără comisioane ascunse, control simplu.',
    taglineEn: 'Designed for students — no hidden fees, simple control.',
    icon: 'building',
    colorVar: '--mb-cat-entertainment',
    rateLabel: 'Fără comisioane de administrare',
    rateLabelEn: 'No maintenance fees',
    benefits: ['Zero comisioane de mentenanță', 'Același control complet din aplicație', 'Poți deschide și contul curent, în paralel'],
    benefitsEn: ['Zero maintenance fees', 'Same full control from the app', 'You can also open the current account, in parallel'],
    requiresDocument: true,
    documentHint: 'Adeverință de student sau carnet — încarci un fișier, verificarea e automată în acest demo.',
    documentHintEn: 'Student certificate or ID card — upload a file, verification is automatic in this demo.',
  },
  // Conturi pe valută REALĂ — necesare pentru Schimb valutar (exchange-service
  // chiar mută soldul între contul curent RON și contul pe valuta asta, nu
  // doar afișează RON convertit). Aceleași culori ca insignele de monedă de
  // pe pagina de schimb — vezi shared/currencies.ts.
  eur: {
    type: 'eur',
    label: 'Cont EUR',
    labelEn: 'EUR account',
    tagline: 'Sold real în euro — folosit direct din Schimb valutar, fără conversie ascunsă.',
    taglineEn: 'Real balance in euros — used directly from Currency Exchange, no hidden conversion.',
    icon: 'globe',
    colorVar: '--mb-blue-600',
    rateLabel: 'Fără dobândă',
    rateLabelEn: 'No interest',
    benefits: ['IBAN propriu, în EUR', 'Alimentat prin Schimb valutar', 'Fără card atașat'],
    benefitsEn: ['Own IBAN, in EUR', 'Funded through Currency Exchange', 'No card attached'],
  },
  usd: {
    type: 'usd',
    label: 'Cont USD',
    labelEn: 'USD account',
    tagline: 'Sold real în dolari — folosit direct din Schimb valutar, fără conversie ascunsă.',
    taglineEn: 'Real balance in US dollars — used directly from Currency Exchange, no hidden conversion.',
    icon: 'globe',
    colorVar: '--mb-positive',
    rateLabel: 'Fără dobândă',
    rateLabelEn: 'No interest',
    benefits: ['IBAN propriu, în USD', 'Alimentat prin Schimb valutar', 'Fără card atașat'],
    benefitsEn: ['Own IBAN, in USD', 'Funded through Currency Exchange', 'No card attached'],
  },
  gbp: {
    type: 'gbp',
    label: 'Cont GBP',
    labelEn: 'GBP account',
    tagline: 'Sold real în lire sterline — folosit direct din Schimb valutar, fără conversie ascunsă.',
    taglineEn: 'Real balance in pounds sterling — used directly from Currency Exchange, no hidden conversion.',
    icon: 'globe',
    colorVar: '--mb-cat-shopping',
    rateLabel: 'Fără dobândă',
    rateLabelEn: 'No interest',
    benefits: ['IBAN propriu, în GBP', 'Alimentat prin Schimb valutar', 'Fără card atașat'],
    benefitsEn: ['Own IBAN, in GBP', 'Funded through Currency Exchange', 'No card attached'],
  },
};

/** Tipurile pe care userul le poate deschide manual (nu include "current" — acela vine automat la înregistrare). */
export const CREATABLE_ACCOUNT_TYPES: CreatableAccountType[] = ['savings', 'student', 'eur', 'usd', 'gbp'];

// --- Accessori RO/EN — mirror pe categories.ts::categoryLabel(value, language) ---

export function accountTypeLabel(meta: AccountTypeMeta, language: Language = 'ro'): string {
  return language === 'en' ? meta.labelEn : meta.label;
}

export function accountTypeTagline(meta: AccountTypeMeta, language: Language = 'ro'): string {
  return language === 'en' ? meta.taglineEn : meta.tagline;
}

export function accountTypeRateLabel(meta: AccountTypeMeta, language: Language = 'ro'): string {
  return language === 'en' ? meta.rateLabelEn : meta.rateLabel;
}

export function accountTypeBenefits(meta: AccountTypeMeta, language: Language = 'ro'): string[] {
  return language === 'en' ? meta.benefitsEn : meta.benefits;
}

export function accountTypeDocumentHint(meta: AccountTypeMeta, language: Language = 'ro'): string | undefined {
  return language === 'en' ? meta.documentHintEn : meta.documentHint;
}
