/**
 * Monede suportate de exchange-service (vezi backend/services/exchange-service/app/config.py) —
 * sursă unică pentru culoarea insignei fiecărei monede în UI (selectoare,
 * lista de cursuri). Reutilizează paleta existentă de accente (aceeași
 * folosită la categorii/avatare), nu inventează culori noi — vezi
 * shared/categories.ts pentru convenția analogă.
 */
export interface CurrencyMeta {
  code: string;
  colorVar: string;
}

const CURRENCIES: CurrencyMeta[] = [
  { code: 'RON', colorVar: '--mb-navy-900' },
  { code: 'EUR', colorVar: '--mb-blue-600' },
  { code: 'USD', colorVar: '--mb-positive' },
  { code: 'GBP', colorVar: '--mb-cat-shopping' },
];

const CURRENCY_MAP = new Map(CURRENCIES.map((c) => [c.code, c]));

export function currencyColorVar(code: string | undefined | null): string {
  if (!code) return '--mb-text-tertiary';
  return CURRENCY_MAP.get(code)?.colorVar ?? '--mb-text-tertiary';
}
