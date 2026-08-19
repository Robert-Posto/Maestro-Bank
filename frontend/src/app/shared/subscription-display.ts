/**
 * Zile rămase până la următoarea facturare a unui abonament, plecând de la
 * ziua lunii (billing_day, 1-31 — vezi Subscription în budgets.service.ts).
 * Dacă billing_day depășește numărul de zile din luna curentă/următoare
 * (ex. 31 în februarie), cădem pe ultima zi a acelei luni — la fel cum se
 * comportă majoritatea abonamentelor reale (Netflix, Spotify etc.).
 * Sursă unică — nu duplica logica de dată în fiecare componentă.
 */
export function daysUntilBilling(billingDay: number, from: Date = new Date()): number {
  const today = new Date(from.getFullYear(), from.getMonth(), from.getDate());

  const billingDateIn = (year: number, month: number): Date => {
    const lastDayOfMonth = new Date(year, month + 1, 0).getDate();
    return new Date(year, month, Math.min(billingDay, lastDayOfMonth));
  };

  let nextBilling = billingDateIn(today.getFullYear(), today.getMonth());
  if (nextBilling < today) {
    nextBilling = billingDateIn(today.getFullYear(), today.getMonth() + 1);
  }

  const msPerDay = 24 * 60 * 60 * 1000;
  return Math.round((nextBilling.getTime() - today.getTime()) / msPerDay);
}

/** Etichetă gata de afișat pentru un număr de zile rămase: "Astăzi", "Mâine" sau "În N zile". */
export function daysRemainingLabel(days: number): string {
  if (days === 0) return 'Astăzi';
  if (days === 1) return 'Mâine';
  return `În ${days} zile`;
}

/** Etichetă gata de afișat pentru un abonament: "Astăzi", "Mâine" sau "În N zile". */
export function daysUntilBillingLabel(billingDay: number, from: Date = new Date()): string {
  return daysRemainingLabel(daysUntilBilling(billingDay, from));
}
