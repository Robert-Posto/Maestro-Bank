import { TranslationEntry } from './index';

export const EXCHANGE_I18N: Record<string, TranslationEntry> = {
  'exchange.title': { ro: 'Schimb valutar', en: 'Currency exchange' },
  'exchange.subtitle': { ro: 'Curs oficial BNR + costuri MaestroBank.', en: 'Official BNR rate + MaestroBank costs.' },
  'exchange.demoBannerText': {
    ro: 'Cursul de bază e cel oficial, publicat zilnic de Banca Națională a României. Spread-ul și comisionul sunt o politică MaestroBank simulată, dar schimbul CHIAR mută soldul — între contul tău curent (RON) și contul tău pe valuta țintă.',
    en: 'The base rate is the official one, published daily by the National Bank of Romania. The spread and commission are simulated MaestroBank policy, but the exchange REALLY moves the balance — between your current (RON) account and your target-currency account.',
  },
  'exchange.youExchange': { ro: 'Schimbi', en: 'You exchange' },
  'exchange.youWillReceive': { ro: 'Vei primi (estimat)', en: 'You will receive (estimated)' },
  'exchange.availableBalance': { ro: 'Sold disponibil:', en: 'Available balance:' },
  'exchange.currentBalance': { ro: 'Sold curent:', en: 'Current balance:' },
  'exchange.noAccountInCurrency': {
    ro: 'Nu ai încă un cont în {currency}.',
    en: "You don't have an account in {currency} yet.",
  },
  'exchange.noAccountInCurrencyOpenFirst': {
    ro: 'Nu ai încă un cont în {currency} — deschide unul înainte de a confirma.',
    en: "You don't have an account in {currency} yet — open one before confirming.",
  },
  'exchange.needAccountForCurrency': {
    ro: 'Ca să primești {currency}, ai nevoie de un cont pe valuta asta.',
    en: 'To receive {currency}, you need an account in that currency.',
  },
  'exchange.openAccountFor': { ro: 'Deschide cont {currency}', en: 'Open {currency} account' },
  'exchange.swapCurrencies': { ro: 'Inversează monedele', en: 'Swap currencies' },
  'exchange.currentMidRate': { ro: 'Curs curent (mid)', en: 'Current rate (mid)' },
  'exchange.appliedRate': { ro: 'Curs aplicat:', en: 'Applied rate:' },
  'exchange.spreadLabel': { ro: 'Spread MaestroBank', en: 'MaestroBank spread' },
  'exchange.spreadIncludedNote': { ro: 'Inclus transparent în curs', en: 'Included transparently in the rate' },
  'exchange.fixedCommission': { ro: 'Comision fix', en: 'Fixed commission' },
  'exchange.shownBeforeConfirm': { ro: 'Afișat înainte de confirmare', en: 'Shown before you confirm' },
  'exchange.totalEstimatedCost': { ro: 'Cost total estimat', en: 'Total estimated cost' },
  'exchange.percentOfAmount': { ro: 'din sumă', en: 'of the amount' },
  'exchange.exchangeCompletedMessage': {
    ro: 'Schimb realizat — soldurile s-au actualizat.',
    en: 'Exchange completed — balances have been updated.',
  },
  'exchange.confirmExchange': { ro: 'Confirmă schimbul', en: 'Confirm exchange' },
  'exchange.howWeCalculateCost': { ro: 'Cum calculăm costul', en: 'How we calculate the cost' },
  'exchange.step1': {
    ro: 'Pornim de la cursul oficial BNR al zilei (mid) — publicat de Banca Națională a României.',
    en: "We start from today's official BNR rate (mid) — published by the National Bank of Romania.",
  },
  'exchange.step2': {
    ro: 'Adăugăm spread-ul MaestroBank — diferența noastră, inclusă transparent în curs.',
    en: 'We add the MaestroBank spread — our margin, included transparently in the rate.',
  },
  'exchange.step3': {
    ro: 'Adăugăm comisionul fix, afișat înainte de confirmare.',
    en: 'We add the fixed commission, shown before you confirm.',
  },
  'exchange.step4': {
    ro: 'Rezultă costul total estimat — exact cât te costă schimbul.',
    en: 'The result is the total estimated cost — exactly what the exchange costs you.',
  },
  'exchange.availableRates': { ro: 'Rate disponibile', en: 'Available rates' },
  'exchange.chooseTwoCurrencies': { ro: 'Alege două monede diferite.', en: 'Choose two different currencies.' },
  'exchange.quoteFailed': {
    ro: 'Nu am putut calcula cursul pentru această pereche.',
    en: 'We could not calculate the rate for this pair.',
  },
  'exchange.executeSuccess': {
    ro: 'Schimb valutar realizat — soldurile s-au actualizat.',
    en: 'Currency exchange completed — balances have been updated.',
  },
  'exchange.executeFailed': { ro: 'Schimbul valutar a eșuat.', en: 'The currency exchange failed.' },
};
