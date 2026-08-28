import { TranslationEntry } from './index';

export const ACCOUNTS_I18N: Record<string, TranslationEntry> = {
  'accounts.title': { ro: 'Conturi', en: 'Accounts' },
  'accounts.subtitle': { ro: 'Toate conturile tale MaestroBank.', en: 'All your MaestroBank accounts.' },
  'accounts.newAccount': { ro: 'Cont nou', en: 'New account' },

  'accounts.loadError': { ro: 'Nu am putut încărca conturile.', en: 'We could not load your accounts.' },
  'accounts.loadErrorTitle': { ro: 'Nu am putut încărca conturile', en: 'We could not load your accounts' },
  'accounts.noAccountsYet': { ro: 'Niciun cont încă', en: 'No accounts yet' },
  'accounts.noAccountsYetDescription': {
    ro: 'Contul tău se creează automat la înregistrare.',
    en: 'Your account is created automatically at registration.',
  },

  'accounts.totalBalance': { ro: 'Sold total', en: 'Total balance' },
  'accounts.currentAccount': { ro: 'Cont curent', en: 'Current account' },
  'accounts.setAside': { ro: 'Pus deoparte', en: 'Set aside' },
  'accounts.accountsOpened': { ro: 'Conturi deschise', en: 'Accounts opened' },

  'accounts.tabAccounts': { ro: 'Conturi', en: 'Accounts' },
  'accounts.tabGoals': { ro: 'Obiective', en: 'Goals' },
  'accounts.tabDeposits': { ro: 'Depozite', en: 'Deposits' },

  'accounts.verified': { ro: 'Verificat', en: 'Verified' },
  'accounts.documentAttachedTitle': { ro: 'Document justificativ atașat', en: 'Supporting document attached' },
  'accounts.availableBalance': { ro: 'Sold disponibil', en: 'Available balance' },
  'accounts.currency': { ro: 'Monedă', en: 'Currency' },
  'accounts.openedAt': { ro: 'Deschis la', en: 'Opened on' },
  'accounts.copyIban': { ro: 'Copiază IBAN', en: 'Copy IBAN' },
  'accounts.transfer': { ro: 'Transfer', en: 'Transfer' },
  'accounts.statement': { ro: 'Extras de cont', en: 'Account statement' },
  'accounts.deleteAccount': { ro: 'Șterge contul', en: 'Delete account' },
  'accounts.currentAccountCannotBeDeleted': {
    ro: 'Contul curent nu poate fi șters',
    en: 'The current account cannot be deleted',
  },
  'accounts.viewAllTransactions': { ro: 'Vezi toate tranzacțiile', en: 'View all transactions' },

  'accounts.savingsGoals': { ro: 'Obiective de economisire', en: 'Savings goals' },
  'accounts.savingsGoalsSubtitle': {
    ro: 'Bani rezervați din contul tău RON — rămân disponibili instant, doar etichetați pentru un scop.',
    en: 'Money set aside from your RON account — stays available instantly, just labeled for a purpose.',
  },
  'accounts.newGoal': { ro: 'Obiectiv nou', en: 'New goal' },
  'accounts.noGoalsYet': { ro: 'Niciun obiectiv încă', en: 'No goals yet' },
  'accounts.noGoalsYetDescription': {
    ro: 'Creează unul pentru vacanță, un fond de urgență sau orice altceva vrei să economisești.',
    en: 'Create one for a vacation, an emergency fund, or anything else you want to save for.',
  },
  'accounts.deleteGoal': { ro: 'Șterge obiectivul', en: 'Delete goal' },
  'accounts.of': { ro: 'din', en: 'of' },
  'accounts.releaseAll': { ro: 'Eliberează tot', en: 'Release all' },
  'accounts.totalAllocated': { ro: 'Total alocat:', en: 'Total allocated:' },
  'accounts.namePlaceholderGoal': { ro: 'Ex: Vacanță', en: 'e.g. Vacation' },
  'accounts.targetAmountLei': { ro: 'Sumă țintă (lei)', en: 'Target amount (RON)' },
  'accounts.createGoal': { ro: 'Creează obiectiv', en: 'Create goal' },
  'accounts.addToGoalPrefix': { ro: "Adaugă la", en: 'Add to' },
  'accounts.amountLei': { ro: 'Sumă (lei)', en: 'Amount (RON)' },

  'accounts.termDeposits': { ro: 'Depozite la termen', en: 'Term deposits' },
  'accounts.termDepositsSubtitle': {
    ro: 'Dobândă mai bună pentru bani pe care nu-i atingi o vreme — RON, EUR, USD sau GBP.',
    en: "Better interest for money you won't touch for a while — RON, EUR, USD, or GBP.",
  },
  'accounts.newDeposit': { ro: 'Depozit nou', en: 'New deposit' },
  'accounts.noDepositsYet': { ro: 'Niciun depozit încă', en: 'No deposits yet' },
  'accounts.noDepositsYetDescription': {
    ro: 'Deschide un depozit la termen pentru o dobândă mai bună decât la un cont de economii.',
    en: 'Open a term deposit for better interest than a savings account.',
  },
  'accounts.months': { ro: 'luni', en: 'months' },
  'accounts.perYear': { ro: 'an', en: 'year' },
  'accounts.daysUntilMaturity': { ro: 'zile până la scadență', en: 'days until maturity' },
  'accounts.estimatedInterest': { ro: 'dobândă estimată', en: 'estimated interest' },
  'accounts.autoRenews': { ro: 'se reînnoiește automat', en: 'auto-renews at maturity' },
  'accounts.liquidateEarly': { ro: 'Lichidează anticipat', en: 'Liquidate early' },
  'accounts.autoRenewedAtMaturity': { ro: 'Reînnoit automat la scadență.', en: 'Auto-renewed at maturity.' },
  'accounts.liquidatedEarlyLostInterest': {
    ro: 'Lichidat anticipat — dobânda a fost pierdută.',
    en: 'Liquidated early — interest was forfeited.',
  },
  'accounts.paidOutAtMaturity': { ro: 'Plătit la scadență, în cont.', en: 'Paid out at maturity, into your account.' },
  'accounts.term': { ro: 'Termen', en: 'Term' },
  'accounts.autoRenewAtMaturity': { ro: 'Reînnoiește automat la scadență', en: 'Automatically renew at maturity' },
  'accounts.openDeposit': { ro: 'Deschide depozitul', en: 'Open the deposit' },
  'accounts.liquidateDepositQ': { ro: 'Lichidezi depozitul anticipat?', en: 'Liquidate the deposit early?' },
  'accounts.liquidateDepositMessage': {
    ro: 'Primești înapoi DOAR suma depusă ({principal}) — dobânda acumulată ({interest}) se pierde integral. Această acțiune nu poate fi anulată.',
    en: 'You get back ONLY the deposited amount ({principal}) — accrued interest ({interest}) is forfeited entirely. This action cannot be undone.',
  },
  'accounts.liquidate': { ro: 'Lichidează', en: 'Liquidate' },

  'accounts.openNewAccount': { ro: 'Deschide un cont nou', en: 'Open a new account' },
  'accounts.allAccountsOpened': { ro: 'Ai deschis toate conturile disponibile', en: "You've opened all available accounts" },
  'accounts.allAccountsOpenedDescription': {
    ro: 'Economii, depozit și student — le ai deja pe toate.',
    en: 'Savings, deposit, and student — you already have them all.',
  },

  'accounts.deleteAccountQ': { ro: 'Șterge contul?', en: 'Delete this account?' },
  'accounts.deleteAccountMessage': {
    ro: 'Sigur vrei să ștergi {type} ({iban})? Această acțiune nu poate fi anulată.',
    en: 'Are you sure you want to delete {type} ({iban})? This action cannot be undone.',
  },

  'accounts.from': { ro: 'De la', en: 'From' },
  'accounts.to': { ro: 'Până la', en: 'To' },
  'accounts.downloadPdf': { ro: 'Descarcă PDF', en: 'Download PDF' },

  'accounts.fillNameAndTarget': {
    ro: 'Completează un nume și o sumă țintă validă.',
    en: 'Fill in a name and a valid target amount.',
  },
  'accounts.goalCreated': { ro: 'Obiectiv "{name}" creat.', en: 'Goal "{name}" created.' },
  'accounts.createGoalError': { ro: 'Nu am putut crea obiectivul.', en: 'We could not create the goal.' },
  'accounts.amountAllocated': { ro: 'Sumă alocată obiectivului.', en: 'Amount allocated to the goal.' },
  'accounts.depositFailed': { ro: 'Depunerea a eșuat.', en: 'The deposit failed.' },
  'accounts.amountReleased': {
    ro: 'Suma a fost eliberată înapoi în contul curent.',
    en: 'The amount was released back to your current account.',
  },
  'accounts.withdrawalFailed': { ro: 'Retragerea a eșuat.', en: 'The withdrawal failed.' },
  'accounts.goalDeleted': { ro: 'Obiectiv șters.', en: 'Goal deleted.' },
  'accounts.deletionFailed': { ro: 'Ștergerea a eșuat.', en: 'The deletion failed.' },
  'accounts.ibanCopied': { ro: 'IBAN copiat în clipboard.', en: 'IBAN copied to clipboard.' },
  'accounts.openAccountError': { ro: 'Nu am putut deschide contul.', en: 'We could not open the account.' },
  'accounts.accountOpenedSuccessfully': { ro: '{type} deschis cu succes.', en: '{type} opened successfully.' },
  'accounts.emptyAccountFirst': {
    ro: 'Golește mai întâi contul — transferă soldul rămas către alt cont al tău, prin Transferuri.',
    en: 'Empty the account first — transfer the remaining balance to another one of your accounts, via Transfers.',
  },
  'accounts.startBeforeEndDate': {
    ro: 'Data de start trebuie să fie înaintea datei de final.',
    en: 'The start date must be before the end date.',
  },
  'accounts.statementGenerated': { ro: 'Extras de cont generat.', en: 'Account statement generated.' },
  'accounts.generateStatementError': {
    ro: 'Nu am putut genera extrasul de cont.',
    en: 'We could not generate the account statement.',
  },
  'accounts.enterValidAmount': { ro: 'Introdu o sumă validă.', en: 'Enter a valid amount.' },
  'accounts.depositOpenedSuccessfully': { ro: 'Depozit deschis cu succes.', en: 'Deposit opened successfully.' },
  'accounts.openDepositError': { ro: 'Nu am putut deschide depozitul.', en: 'We could not open the deposit.' },
  'accounts.depositLiquidated': {
    ro: 'Depozit lichidat — suma a revenit în cont.',
    en: 'Deposit liquidated — the amount was returned to your account.',
  },
  'accounts.liquidateDepositError': { ro: 'Nu am putut lichida depozitul.', en: 'We could not liquidate the deposit.' },
  'accounts.accountDeleted': { ro: '{type} șters.', en: '{type} deleted.' },
  'accounts.deleteAccountError': { ro: 'Nu am putut șterge contul.', en: 'We could not delete the account.' },

  // Folosite de AccountTypeCarousel (shared/components/account-type-carousel) — vezi și account-types.ts.
  'accounts.attachDocument': { ro: 'Atașează document (PDF/imagine)', en: 'Attach document (PDF/image)' },
  'accounts.carouselPrev': { ro: 'Anterior', en: 'Previous' },
  'accounts.carouselNext': { ro: 'Următorul', en: 'Next' },
  'accounts.openAccountTypeCta': { ro: 'Deschide', en: 'Open' },
  'accounts.viewType': { ro: 'Vezi', en: 'View' },
};
