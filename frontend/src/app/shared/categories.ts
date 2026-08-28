import { Language } from '../services/language.service';

/**
 * Categorii de tranzacții/bugete — trebuie să corespundă EXACT cu
 * TRANSACTION_CATEGORIES din backend/services/transactions-service/app/models.py.
 * Sursă unică pentru label RO/EN + culoare — nu hardcoda categoriile separat
 * în fiecare componentă (vezi task-ul MaestroBank, secțiunea 17).
 */
export interface CategoryMeta {
  value: string;
  label: string;
  labelEn: string;
  colorVar: string;
}

export const TRANSACTION_CATEGORIES: CategoryMeta[] = [
  { value: 'groceries', label: 'Alimentație', labelEn: 'Groceries', colorVar: '--mb-cat-groceries' },
  { value: 'shopping', label: 'Shopping', labelEn: 'Shopping', colorVar: '--mb-cat-shopping' },
  { value: 'transport', label: 'Transport', labelEn: 'Transport', colorVar: '--mb-cat-transport' },
  { value: 'bills', label: 'Facturi', labelEn: 'Bills', colorVar: '--mb-cat-bills' },
  { value: 'restaurants', label: 'Restaurante', labelEn: 'Restaurants', colorVar: '--mb-cat-restaurants' },
  { value: 'entertainment', label: 'Entertainment', labelEn: 'Entertainment', colorVar: '--mb-cat-entertainment' },
  { value: 'subscriptions', label: 'Abonamente', labelEn: 'Subscriptions', colorVar: '--mb-cat-subscriptions' },
  { value: 'income', label: 'Venit', labelEn: 'Income', colorVar: '--mb-cat-income' },
  { value: 'other', label: 'Altele', labelEn: 'Other', colorVar: '--mb-cat-other' },
];

const CATEGORY_MAP = new Map(TRANSACTION_CATEGORIES.map((c) => [c.value, c]));

export function categoryLabel(value: string | undefined | null, language: Language = 'ro'): string {
  if (!value) return language === 'en' ? 'Other' : 'Altele';
  const meta = CATEGORY_MAP.get(value);
  if (!meta) return value;
  return language === 'en' ? meta.labelEn : meta.label;
}

export function categoryColorVar(value: string | undefined | null): string {
  if (!value) return '--mb-cat-other';
  return CATEGORY_MAP.get(value)?.colorVar ?? '--mb-cat-other';
}
