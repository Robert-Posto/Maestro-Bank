import { TranslationEntry } from './index';

export const INVESTMENTS_I18N: Record<string, TranslationEntry> = {
  'investments.title': { ro: 'Investiții', en: 'Investments' },
  'investments.subtitle': {
    ro: 'Cumpără și vinde acțiuni și ETF-uri, cu preț real de piață.',
    en: 'Buy and sell stocks and ETFs at real market prices.',
  },
  'investments.needUsdAccountTitle': { ro: 'Ai nevoie de un cont USD', en: 'You need a USD account' },
  'investments.needUsdAccountDescription': {
    ro: 'Toate instrumentele se tranzacționează în USD — deschide un cont USD din pagina Conturi înainte de a investi.',
    en: 'All instruments trade in USD — open a USD account from the Accounts page before investing.',
  },
  'investments.openUsdAccount': { ro: 'Deschide cont USD', en: 'Open USD account' },

  'investments.portfolioValue': { ro: 'Valoare portofoliu', en: 'Portfolio value' },
  'investments.unrealizedGainLoss': { ro: 'Câștig/pierdere nerealizat(ă)', en: 'Unrealized gain/loss' },
  'investments.availableBalanceUsd': { ro: 'Sold disponibil (USD)', en: 'Available balance (USD)' },

  'investments.yourPortfolio': { ro: 'Portofoliul tău', en: 'Your portfolio' },
  'investments.noInstrumentsYet': { ro: 'Niciun instrument încă', en: 'No instruments yet' },
  'investments.noInstrumentsDescription': {
    ro: 'Alege ceva din catalogul de mai jos ca să începi.',
    en: 'Pick something from the catalog below to get started.',
  },
  'investments.symbol': { ro: 'Simbol', en: 'Symbol' },
  'investments.quantity': { ro: 'Cantitate', en: 'Quantity' },
  'investments.avgPrice': { ro: 'Preț mediu', en: 'Average price' },
  'investments.currentPrice': { ro: 'Preț curent', en: 'Current price' },
  'investments.value': { ro: 'Valoare', en: 'Value' },
  'investments.gainLoss': { ro: 'Câștig/pierdere', en: 'Gain/loss' },
  'investments.actionsAria': { ro: 'Acțiuni', en: 'Actions' },
  'investments.sell': { ro: 'Vinde', en: 'Sell' },

  'investments.marketIndices': { ro: 'Indici bursieri', en: 'Market indices' },
  'investments.indicesSubtitle': {
    ro: 'Informativ — un indice nu se cumpără direct; SPY/QQQ din catalogul de mai jos sunt ETF-urile care-l urmăresc.',
    en: 'Informational only — an index cannot be bought directly; SPY/QQQ in the catalog below are the ETFs that track it.',
  },

  'investments.catalog': { ro: 'Catalog', en: 'Catalog' },
  'investments.allCategories': { ro: 'Toate', en: 'All' },
  'investments.categoryTechnology': { ro: 'Tehnologie', en: 'Technology' },
  'investments.categoryConsumerFinance': { ro: 'Consum & Finanțe', en: 'Consumer & Finance' },
  'investments.categoryEtfs': { ro: 'ETF-uri', en: 'ETFs' },
  'investments.categoryOther': { ro: 'Altele', en: 'Other' },
  'investments.instrumentsSuffix': { ro: 'instrumente', en: 'instruments' },
  'investments.buy': { ro: 'Cumpără', en: 'Buy' },

  'investments.couldNotLoadDetails': { ro: 'Nu am putut încărca detaliile', en: 'We could not load the details' },
  'investments.dayRange': { ro: 'Interval zi', en: 'Day range' },
  'investments.week52Range': { ro: '52 săptămâni', en: '52 weeks' },
  'investments.volumeLabel': { ro: 'Volum:', en: 'Volume:' },
  'investments.shares': { ro: 'acțiuni', en: 'shares' },
  'investments.indexInfoNote': {
    ro: 'Indice informativ — nu se tranzacționează direct.',
    en: 'Informational index — not directly tradable.',
  },

  'investments.currentPriceLabel': { ro: 'Preț curent:', en: 'Current price:' },
  'investments.currentPriceInline': { ro: 'preț curent', en: 'current price' },
  'investments.perShare': { ro: '/ acțiune', en: '/ share' },
  'investments.amountUsd': { ro: 'Sumă (USD)', en: 'Amount (USD)' },
  'investments.confirmBuy': { ro: 'Confirmă cumpărarea', en: 'Confirm purchase' },

  'investments.youHold': { ro: 'Deții', en: 'You hold' },
  'investments.approxReceived': { ro: 'încasați', en: 'received' },
  'investments.confirmSell': { ro: 'Confirmă vânzarea', en: 'Confirm sale' },

  'investments.detailLoadError': { ro: 'Nu am putut încărca detaliile.', en: 'We could not load the details.' },
  'investments.boughtMessage': { ro: 'Ai cumpărat {symbol} de {amount} USD.', en: 'You bought {symbol} for {amount} USD.' },
  'investments.buyFailed': { ro: 'Cumpărarea a eșuat.', en: 'The purchase failed.' },
  'investments.soldMessage': { ro: 'Ai vândut {quantity} {symbol}.', en: 'You sold {quantity} {symbol}.' },
  'investments.sellFailed': { ro: 'Vânzarea a eșuat.', en: 'The sale failed.' },
};
