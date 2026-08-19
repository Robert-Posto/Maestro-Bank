import { AccountType, CreatableAccountType } from '../services/banking.service';

/**
 * Catalog STATIC cu tipurile de cont — folosit la deschiderea unui cont nou
 * (Accounts feature) și la afișarea etichetei/culorii unui cont existent.
 * Ratele/beneficiile sunt informative (ca la orice catalog de produse
 * bancare), NU sunt simulate/acumulate automat — nu există încă un job care
 * să calculeze dobândă reală (la fel cum "Financial Guardian" e marcat
 * "Coming in AI phase" în altă parte a aplicației, nu promitem ceva ce nu
 * rulează efectiv).
 */
export interface AccountTypeMeta {
  type: AccountType;
  label: string;
  tagline: string;
  icon: string;
  colorVar: string;
  rateLabel: string;
  benefits: string[];
  /** Necesită un document justificativ înainte de deschidere (ex. student → adeverință/carnet). */
  requiresDocument?: boolean;
  documentHint?: string;
}

export const ACCOUNT_TYPE_CATALOG: Record<AccountType, AccountTypeMeta> = {
  current: {
    type: 'current',
    label: 'Cont curent',
    tagline: 'Contul tău principal, pentru cheltuieli și transferuri zilnice.',
    icon: 'wallet',
    colorVar: '--mb-blue-500',
    rateLabel: 'Fără dobândă',
    benefits: ['Card atașat, activ imediat', 'Transferuri și plăți nelimitate', 'Fără sold minim'],
  },
  savings: {
    type: 'savings',
    label: 'Cont de economii',
    tagline: 'Pui bani deoparte, separat de cheltuielile zilnice, cu acces oricând.',
    icon: 'sparkles',
    colorVar: '--mb-cat-groceries',
    rateLabel: '~3,5%/an, indicativ',
    benefits: ['IBAN propriu, separat de contul curent', 'Retragi oricând, fără penalizări', 'Fără card atașat'],
  },
  deposit: {
    type: 'deposit',
    label: 'Cont de depozit',
    tagline: 'Dobândă mai bună pentru bani pe care nu-i atingi o vreme.',
    icon: 'shield',
    colorVar: '--mb-cat-bills',
    rateLabel: '~5,8%/an, indicativ',
    benefits: ['Randament mai mare decât economiile', 'Ideal pentru un obiectiv pe termen mediu', 'IBAN propriu, urmărit separat'],
  },
  student: {
    type: 'student',
    label: 'Cont student',
    tagline: 'Gândit pentru studenți — fără comisioane ascunse, control simplu.',
    icon: 'building',
    colorVar: '--mb-cat-entertainment',
    rateLabel: 'Fără comisioane de administrare',
    benefits: ['Zero comisioane de mentenanță', 'Același control complet din aplicație', 'Poți deschide și contul curent, în paralel'],
    requiresDocument: true,
    documentHint: 'Adeverință de student sau carnet — încarci un fișier, verificarea e automată în acest demo.',
  },
};

/** Tipurile pe care userul le poate deschide manual (nu include "current" — acela vine automat la înregistrare). */
export const CREATABLE_ACCOUNT_TYPES: CreatableAccountType[] = ['savings', 'deposit', 'student'];
