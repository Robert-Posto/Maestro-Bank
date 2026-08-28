import { TranslationEntry } from './index';

/** Pagina Credite (features/loans) — simulator de rată, listă credite,
 * plată anticipată, istoric plăți, plus cartea glisabilă "Cum funcționează".
 * Cheile `howItWorks.*` sunt consumate de un `computed()` în loans.ts, la
 * fel ca `copilot.suggestedQ*`. */
export const LOANS_I18N: Record<string, TranslationEntry> = {
  'loans.title': { ro: 'Credite', en: 'Loans' },
  'loans.subtitle': {
    ro: 'Vezi exact cât te costă un credit, înainte să aplici.',
    en: 'See exactly what a loan costs you before you apply.',
  },

  'loans.howItWorksTitle': { ro: 'Cum funcționează, pas cu pas', en: 'How it works, step by step' },
  'loans.howItWorksSubtitle': {
    ro: 'Glisează stânga-dreapta prin cărți — de la sumă la rată automată.',
    en: 'Swipe left and right through the cards — from amount to automatic instalment.',
  },
  'loans.deckNote': {
    ro: 'Aprobăm un credit doar dacă rata lui (împreună cu cele active deja) nu depășește 40% din venitul tău mediu lunar — o politică simplă, ca să nu te împrumuți peste ce-ți poți permite.',
    en: "We approve a loan only if its instalment (together with any active ones) stays under 40% of your average monthly income — a simple policy so you don't borrow beyond what you can afford.",
  },
  'loans.simulateCta': { ro: 'Simulează rata ta →', en: 'Simulate your instalment →' },

  'loans.amount': { ro: 'Sumă', en: 'Amount' },
  'loans.term': { ro: 'Termen', en: 'Term' },
  'loans.monthsShort': { ro: 'luni', en: 'months' },
  'loans.perYearSuffix': { ro: '/an', en: '/year' },

  'loans.monthlyInstalmentEstimated': { ro: 'Rata ta lunară, estimată', en: 'Your monthly instalment, estimated' },
  'loans.totalPaid': { ro: 'Total plătit', en: 'Total paid' },
  'loans.ofWhichInterest': { ro: 'Din care dobândă', en: 'Of which interest' },
  'loans.applyForThisLoan': { ro: 'Aplică pentru acest credit', en: 'Apply for this loan' },
  'loans.estimateDisclaimer': {
    ro: 'Estimare — verificăm eligibilitatea reală când aplici.',
    en: 'Estimate — we check your real eligibility when you apply.',
  },

  'loans.yourLoans': { ro: 'Creditele tale', en: 'Your loans' },
  'loans.noLoansTitle': { ro: 'Niciun credit încă', en: 'No loans yet' },
  'loans.noLoansDesc': {
    ro: 'Folosește simulatorul de mai sus ca să vezi rata și să aplici.',
    en: 'Use the simulator above to see the instalment and apply.',
  },
  'loans.paymentsProgress': { ro: '{made} din {total} rate plătite', en: '{made} of {total} instalments paid' },
  'loans.monthlyInstalment': { ro: 'Rată lunară', en: 'Monthly instalment' },
  'loans.outstanding': { ro: 'Rest de plată', en: 'Outstanding' },
  'loans.nextInstalment': { ro: 'Următoarea rată', en: 'Next instalment' },
  'loans.inDays': { ro: 'peste {n} zile', en: 'in {n} days' },
  'loans.paymentHistory': { ro: 'Istoric plăți', en: 'Payment history' },
  'loans.earlyPayoff': { ro: 'Plată anticipată', en: 'Early payoff' },

  'loans.confirmApplyTitle': { ro: 'Confirmă cererea de credit', en: 'Confirm your loan application' },
  'loans.termWithRate': { ro: '{months} luni ({rate}%/an)', en: '{months} months ({rate}%/year)' },
  'loans.estimatedMonthlyInstalment': { ro: 'Rată lunară estimată', en: 'Estimated monthly instalment' },
  'loans.applyConfirmHint': {
    ro: 'Verificăm eligibilitatea reală acum — dacă rata depășește ce-ți poți permite, cererea e respinsă, cu motivul exact.',
    en: "We check your real eligibility now — if the instalment exceeds what you can afford, the application is rejected, with the exact reason.",
  },
  'loans.submitApplication': { ro: 'Trimite cererea', en: 'Submit application' },

  'loans.payoffTextBefore': { ro: 'Achiți acum', en: 'You now pay off' },
  'loans.payoffTextAfter': {
    ro: '(restul de principal, fără dobândă suplimentară) și creditul se închide. Confirmi?',
    en: '(the remaining principal, with no extra interest) and the loan closes. Confirm?',
  },
  'loans.confirmPayment': { ro: 'Confirmă plata', en: 'Confirm payment' },

  'loans.noPaymentsTitle': { ro: 'Nicio plată încă', en: 'No payments yet' },
  'loans.noPaymentsDesc': {
    ro: 'Prima rată apare aici după ce se debitează automat.',
    en: 'The first instalment appears here after it is automatically debited.',
  },
  'loans.tableDate': { ro: 'Data', en: 'Date' },
  'loans.tableAmount': { ro: 'Sumă', en: 'Amount' },
  'loans.tableInterest': { ro: 'Dobândă', en: 'Interest' },
  'loans.tablePrincipal': { ro: 'Principal', en: 'Principal' },
  'loans.tableRemaining': { ro: 'Rest', en: 'Remaining' },

  'loans.approvedToast': {
    ro: 'Creditul a fost aprobat — suma e deja în contul tău curent.',
    en: 'The loan was approved — the amount is already in your current account.',
  },
  'loans.applyRejected': { ro: 'Cererea de credit a fost respinsă.', en: 'The loan application was rejected.' },
  'loans.payoffDoneToast': { ro: 'Credit achitat anticipat.', en: 'Loan paid off early.' },
  'loans.payoffFailed': { ro: 'Plata anticipată a eșuat.', en: 'The early payoff failed.' },

  // --- Cartea glisabilă "Cum funcționează" (loans.ts::HOW_IT_WORKS_CARDS) ---
  'loans.howItWorks.coverTitle': {
    ro: 'Cum funcționează un credit MaestroBank',
    en: 'How a MaestroBank loan works',
  },
  'loans.howItWorks.coverText': {
    ro: 'Patru pași, fără birocrație — glisează pentru următorul.',
    en: 'Four steps, no paperwork — swipe for the next one.',
  },
  'loans.howItWorks.step1Title': { ro: 'Alegi suma și termenul', en: 'Choose the amount and the term' },
  'loans.howItWorks.step1Text': {
    ro: 'Simulatorul de mai jos îți arată rata exactă înainte să aplici — fără surprize.',
    en: 'The simulator below shows the exact instalment before you apply — no surprises.',
  },
  'loans.howItWorks.step2Title': { ro: 'Verificăm venitul tău real', en: 'We check your real income' },
  'loans.howItWorks.step2Text': {
    ro: 'Ne uităm la istoricul tău de tranzacții din ultimele 3 luni, nu la ce declari.',
    en: 'We look at your transaction history from the last 3 months, not at what you declare.',
  },
  'loans.howItWorks.step3Title': { ro: 'Banii intră imediat în cont', en: 'The money arrives in your account right away' },
  'loans.howItWorks.step3Text': {
    ro: 'Fără așteptare, fără aprobare manuală — dacă eligibilitatea e îndeplinită.',
    en: 'No waiting, no manual approval — as long as you meet the eligibility check.',
  },
  'loans.howItWorks.step4Title': { ro: 'Rata se plătește singură', en: 'The instalment pays itself' },
  'loans.howItWorks.step4Text': {
    ro: 'Automat, lunar, din contul curent — sau achiți oricând tot restul, fără cost suplimentar.',
    en: 'Automatically, monthly, from your current account — or pay off the rest anytime, at no extra cost.',
  },
  'loans.howItWorks.benefitInstantTitle': { ro: 'Aprobare pe loc', en: 'Instant approval' },
  'loans.howItWorks.benefitInstantText': {
    ro: 'Verificăm venitul tău real, din istoric — nu aștepți zile pentru un răspuns.',
    en: "We check your real income from your history — you don't wait days for an answer.",
  },
  'loans.howItWorks.benefitNoHiddenTitle': { ro: 'Fără costuri ascunse', en: 'No hidden costs' },
  'loans.howItWorks.benefitNoHiddenText': {
    ro: 'Rata din simulator e exact ce plătești — fără comisioane suplimentare.',
    en: 'The instalment in the simulator is exactly what you pay — no extra fees.',
  },
  'loans.howItWorks.benefitAutoTitle': { ro: 'Plată automată', en: 'Automatic payment' },
  'loans.howItWorks.benefitAutoText': {
    ro: 'Rata se scade singură din cont, lunar — nu ții tu evidența.',
    en: "The instalment is deducted from your account automatically, monthly — you don't have to track it.",
  },
  'loans.howItWorks.benefitPayoffTitle': { ro: 'Achiți oricând', en: 'Pay off anytime' },
  'loans.howItWorks.benefitPayoffText': {
    ro: 'Plată anticipată, fără dobândă suplimentară pentru perioada rămasă.',
    en: 'Early payoff, with no extra interest for the remaining period.',
  },
};
