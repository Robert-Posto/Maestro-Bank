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
    ro: 'Recomandăm aprobarea doar dacă rata (împreună cu cele active deja) nu depășește 40% din venitul tău mediu lunar — un ofițer de credit vede acest semnal și decide.',
    en: 'We recommend approval only if the instalment (together with any active ones) stays under 40% of your average monthly income — a loan officer sees this signal and decides.',
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

  'loans.confirmApplyTitle': { ro: 'Cerere de credit', en: 'Loan application' },
  'loans.termWithRate': { ro: '{months} luni ({rate}%/an)', en: '{months} months ({rate}%/year)' },
  'loans.estimatedMonthlyInstalment': { ro: 'Rată lunară estimată', en: 'Estimated monthly instalment' },
  'loans.applyConfirmHint': {
    ro: 'Ca la o cerere reală de credit, avem nevoie de câteva răspunsuri — cererea ta merge apoi la un ofițer de credit, care decide după ce analizează venitul tău real.',
    en: 'Like a real loan application, we need a few answers — your application then goes to a loan officer, who decides after reviewing your real income.',
  },

  'loans.field.sectionTitle': { ro: 'Câteva întrebări despre situația ta', en: 'A few questions about your situation' },
  'loans.field.purpose': { ro: 'Scopul creditului', en: 'Purpose of the loan' },
  'loans.field.employmentStatus': { ro: 'Statutul profesional', en: 'Employment status' },
  'loans.field.employmentTenure': { ro: 'Vechime la locul actual', en: 'Tenure in your current role' },
  'loans.field.incomeSource': { ro: 'Sursa venitului', en: 'Source of income' },
  'loans.field.incomeSourcePlaceholder': { ro: 'Ex. Angajator SRL, sau descrie venitul', en: 'E.g. your employer, or describe your income' },
  'loans.field.declaredIncome': { ro: 'Venit lunar net declarat (RON)', en: 'Declared net monthly income (RON)' },
  'loans.field.dependentsCount': { ro: 'Persoane în întreținere', en: 'Dependents' },
  'loans.field.hasOtherDebts': { ro: 'Ai alte credite/rate în derulare?', en: 'Do you have other loans/instalments running?' },
  'loans.field.otherDebtsAmount': { ro: 'Rata lunară totală la celelalte credite (RON)', en: 'Total monthly instalment on other loans (RON)' },
  'loans.field.consent': {
    ro: 'Sunt de acord ca MaestroBank să îmi verifice istoricul de tranzacții pentru evaluarea acestei cereri.',
    en: 'I agree that MaestroBank may review my transaction history to evaluate this application.',
  },

  'loans.purpose.personal_needs': { ro: 'Nevoi personale', en: 'Personal needs' },
  'loans.purpose.home_renovation': { ro: 'Renovarea locuinței', en: 'Home renovation' },
  'loans.purpose.purchase_goods': { ro: 'Achiziție bunuri', en: 'Purchasing goods' },
  'loans.purpose.debt_refinancing': { ro: 'Refinanțare datorii', en: 'Debt refinancing' },
  'loans.purpose.education': { ro: 'Educație', en: 'Education' },
  'loans.purpose.medical': { ro: 'Cheltuieli medicale', en: 'Medical expenses' },
  'loans.purpose.vacation': { ro: 'Vacanță', en: 'Vacation' },
  'loans.purpose.other': { ro: 'Altul', en: 'Other' },

  'loans.employmentStatus.employed_permanent': { ro: 'Angajat, contract nedeterminat', en: 'Employed, permanent contract' },
  'loans.employmentStatus.employed_fixed_term': { ro: 'Angajat, contract determinat', en: 'Employed, fixed-term contract' },
  'loans.employmentStatus.self_employed': { ro: 'Liber profesionist / PFA', en: 'Self-employed' },
  'loans.employmentStatus.retired': { ro: 'Pensionar', en: 'Retired' },
  'loans.employmentStatus.student': { ro: 'Student', en: 'Student' },
  'loans.employmentStatus.unemployed': { ro: 'Fără loc de muncă', en: 'Unemployed' },

  'loans.employmentTenure.under_6_months': { ro: 'Sub 6 luni', en: 'Under 6 months' },
  'loans.employmentTenure.6_to_12_months': { ro: '6-12 luni', en: '6-12 months' },
  'loans.employmentTenure.1_to_3_years': { ro: '1-3 ani', en: '1-3 years' },
  'loans.employmentTenure.3_to_5_years': { ro: '3-5 ani', en: '3-5 years' },
  'loans.employmentTenure.over_5_years': { ro: 'Peste 5 ani', en: 'Over 5 years' },

  'loans.submitApplication': { ro: 'Trimite cererea', en: 'Submit application' },
  'loans.applicationSubmittedToast': {
    ro: 'Cererea a fost trimisă — un ofițer de credit o analizează, te anunțăm cu decizia.',
    en: "Application submitted — a loan officer is reviewing it, we'll notify you with the decision.",
  },
  'loans.applySubmitError': { ro: 'Trimiterea cererii a eșuat.', en: 'Submitting the application failed.' },

  'loans.status.pending_review': { ro: 'În analiză', en: 'Under review' },
  'loans.status.active': { ro: 'Activ', en: 'Active' },
  'loans.status.rejected': { ro: 'Respinsă', en: 'Rejected' },
  'loans.status.paid_off': { ro: 'Achitat', en: 'Paid off' },
  'loans.pendingReviewNote': {
    ro: 'Cererea ta e în analiza unui ofițer de credit. Te anunțăm imediat ce e o decizie.',
    en: "Your application is with a loan officer for review. We'll let you know as soon as there's a decision.",
  },
  'loans.rejectionReasonLabel': { ro: 'Motiv:', en: 'Reason:' },

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
  'loans.howItWorks.step3Title': { ro: 'Un ofițer de credit analizează cererea', en: 'A loan officer reviews the application' },
  'loans.howItWorks.step3Text': {
    ro: 'Cu venitul tău real și chestionarul completat sub ochi, decide — banii intră în cont doar la aprobare.',
    en: 'With your real income and completed questionnaire in front of them, they decide — the money lands in your account only on approval.',
  },
  'loans.howItWorks.step4Title': { ro: 'Rata se plătește singură', en: 'The instalment pays itself' },
  'loans.howItWorks.step4Text': {
    ro: 'Automat, lunar, din contul curent — sau achiți oricând tot restul, fără cost suplimentar.',
    en: 'Automatically, monthly, from your current account — or pay off the rest anytime, at no extra cost.',
  },
  'loans.howItWorks.benefitInstantTitle': { ro: 'Decizie informată', en: 'Informed decision' },
  'loans.howItWorks.benefitInstantText': {
    ro: 'Ofițerul de credit vede venitul tău real, din istoric — nu doar ce declari.',
    en: "The loan officer sees your real income from your history — not just what you declare.",
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
