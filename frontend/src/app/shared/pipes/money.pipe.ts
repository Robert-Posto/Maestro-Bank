import { Pipe, PipeTransform } from '@angular/core';

/**
 * Formatare centralizată a sumelor monetare. Backendul NU folosește
 * niciodată float pentru bani (vezi *_minor peste tot în API) — acest
 * pipe e SINGURUL loc din frontend care transformă bani-întregi în text
 * afișabil. Nu reface formatarea inline în componente.
 *
 * Uz: `{{ amountMinor | money }}` -> "1.234,56 lei"
 *     `{{ amountMinor | money:'EUR':false }}` -> "1.234,56" (fără simbol)
 */
@Pipe({ name: 'money', standalone: true })
export class MoneyPipe implements PipeTransform {
  transform(amountMinor: number | null | undefined, currency = 'RON', withSymbol = true): string {
    if (amountMinor === null || amountMinor === undefined || Number.isNaN(amountMinor)) {
      return '—';
    }

    const major = amountMinor / 100;
    const formatted = new Intl.NumberFormat('ro-RO', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(major);

    if (!withSymbol) {
      return formatted;
    }

    const symbol = currency === 'RON' ? 'lei' : currency;
    return `${formatted} ${symbol}`;
  }
}

/** Variantă non-pipe, pentru folosire în cod TS (ex. export CSV, titluri dinamice). */
export function formatMoneyMinor(amountMinor: number, currency = 'RON', withSymbol = true): string {
  const major = amountMinor / 100;
  const formatted = new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(
    major,
  );
  if (!withSymbol) {
    return formatted;
  }
  return `${formatted} ${currency === 'RON' ? 'lei' : currency}`;
}
