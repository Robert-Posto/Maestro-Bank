/**
 * Numele de afișat pentru o tranzacție: prioritate
 * counterparty_name (transfer către/de la un user MaestroBank real, ex.
 * "Andrei Popescu") > description (ex. numele comerciantului, "Kaufland")
 * > counterparty_iban (fallback dacă nu avem nimic altceva).
 * Sursă unică — nu duplica fallback-ul în fiecare componentă.
 */
export function transactionDisplayName(tx: {
  description?: string | null;
  counterparty_name?: string | null;
  counterparty_iban: string;
}): string {
  return tx.counterparty_name?.trim() || tx.description?.trim() || tx.counterparty_iban;
}
