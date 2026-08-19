/**
 * Categorii de tranzacții/bugete — trebuie să corespundă EXACT cu
 * TRANSACTION_CATEGORIES din backend/services/transactions-service/app/models.py.
 * Sursă unică pentru label RO + culoare — nu hardcoda categoriile separat
 * în fiecare componentă (vezi task-ul MaestroBank, secțiunea 17).
 */
export interface CategoryMeta {
  value: string;
  label: string;
  colorVar: string;
}

export const TRANSACTION_CATEGORIES: CategoryMeta[] = [
  { value: 'groceries', label: 'Alimentație', colorVar: '--mb-cat-groceries' },
  { value: 'shopping', label: 'Shopping', colorVar: '--mb-cat-shopping' },
  { value: 'transport', label: 'Transport', colorVar: '--mb-cat-transport' },
  { value: 'bills', label: 'Facturi', colorVar: '--mb-cat-bills' },
  { value: 'restaurants', label: 'Restaurante', colorVar: '--mb-cat-restaurants' },
  { value: 'entertainment', label: 'Entertainment', colorVar: '--mb-cat-entertainment' },
  { value: 'subscriptions', label: 'Abonamente', colorVar: '--mb-cat-subscriptions' },
  { value: 'income', label: 'Venit', colorVar: '--mb-cat-income' },
  { value: 'other', label: 'Altele', colorVar: '--mb-cat-other' },
];

const CATEGORY_MAP = new Map(TRANSACTION_CATEGORIES.map((c) => [c.value, c]));

export function categoryLabel(value: string | undefined | null): string {
  if (!value) return 'Altele';
  return CATEGORY_MAP.get(value)?.label ?? value;
}

export function categoryColorVar(value: string | undefined | null): string {
  if (!value) return '--mb-cat-other';
  return CATEGORY_MAP.get(value)?.colorVar ?? '--mb-cat-other';
}
