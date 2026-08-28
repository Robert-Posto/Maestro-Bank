import { TranslationEntry } from './index';

export const FORECAST_I18N: Record<string, TranslationEntry> = {
  'forecast.subtitle': {
    ro: 'Analiză determinist calculată din tranzacțiile tale — fără AI.',
    en: 'Deterministic analysis calculated from your transactions — no AI.',
  },
  'forecast.loadError': { ro: 'Nu am putut încărca analiza cheltuielilor.', en: 'We could not load your spending analysis.' },
  'forecast.loadErrorTitle': { ro: 'Nu am putut încărca analiza', en: 'We could not load the analysis' },
  'forecast.spendingThisMonth': { ro: 'Cheltuieli luna aceasta', en: 'Spending this month' },
  'forecast.dailyAverage': { ro: 'Medie zilnică cheltuită', en: 'Average daily spending' },
  'forecast.byCategory': { ro: 'Cheltuieli pe categorie', en: 'Spending by category' },
  'forecast.noSpendingThisMonth': { ro: 'Nicio cheltuială luna aceasta', en: 'No spending this month' },
  'forecast.cashFlowPrefix': { ro: 'Cash-flow — ultimele', en: 'Cash flow — last' },
  'forecast.days': { ro: 'zile', en: 'days' },
  'forecast.chartAriaLabel': { ro: 'Grafic cash-flow net pe zi', en: 'Chart of daily net cash flow' },
  'forecast.notEnoughData': { ro: 'Fără date suficiente', en: 'Not enough data' },
  'forecast.leiUnit': { ro: 'lei', en: 'RON' },
  'forecast.dailyNetFlowCaption': {
    ro: 'Flux net zilnic (încasări − plăți). Punctele deasupra liniei punctate = zi pozitivă.',
    en: 'Daily net flow (income − payments). Points above the dotted line = a positive day.',
  },
  'forecast.monthlyForecast': { ro: 'Forecast lunar', en: 'Monthly forecast' },
  'forecast.currentBalance': { ro: 'Sold curent', en: 'Current balance' },
  'forecast.estimatedExpenses': { ro: 'Cheltuieli estimate', en: 'Estimated expenses' },
  'forecast.daysRemainingInMonth': { ro: 'Zile rămase în lună', en: 'Days remaining in month' },
  'forecast.estimatedEndOfMonthBalance': { ro: 'Sold estimat la final de lună', en: 'Estimated end-of-month balance' },
  'forecast.upcomingObligations': { ro: 'Obligații viitoare', en: 'Upcoming obligations' },
};
