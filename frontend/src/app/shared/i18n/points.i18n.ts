import { TranslationEntry } from './index';

/** Pagina Puncte & Recompense (features/points) — sold puncte, rate de
 * câștig pe categorie, catalog de recompense, roata norocului, bonus de
 * bun-venit, plus cartea glisabilă "Cum funcționează". Cheile
 * `howItWorks.*` sunt consumate de un `computed()` în points.ts. */
export const POINTS_I18N: Record<string, TranslationEntry> = {
  'points.title': { ro: 'Puncte & Recompense', en: 'Points & Rewards' },
  'points.subtitle': {
    ro: 'Câștigi puncte la plățile către comercianți, le răscumperi pentru cashback sau le pariezi la roata norocului.',
    en: 'You earn points on payments to merchants, redeem them for cashback, or wager them on the wheel of fortune.',
  },

  'points.howItWorksTitle': { ro: 'Cum funcționează, pas cu pas', en: 'How it works, step by step' },
  'points.howItWorksSubtitle': {
    ro: 'Glisează stânga-dreapta prin cărți — de la o cumpărătură la cashback în cont.',
    en: 'Swipe left and right through the cards — from a purchase to cashback in your account.',
  },

  'points.pointsWord': { ro: 'puncte', en: 'points' },

  'points.welcomeBannerTitle': { ro: 'Ai {n} puncte de bun-venit, nerevendicate', en: 'You have {n} unclaimed welcome points' },
  'points.welcomeBannerSubtitle': {
    ro: 'Le poți folosi imediat pentru prima ta recompensă.',
    en: 'You can use them right away for your first reward.',
  },
  'points.claim': { ro: 'Revendică', en: 'Claim' },

  'points.pointsBalance': { ro: 'Sold puncte', en: 'Points balance' },
  'points.balanceHint': {
    ro: 'Câștigi puncte doar la plăți către comercianți (nu la transferuri către alți useri MaestroBank) — vezi ratele pe categorie mai jos.',
    en: 'You earn points only on payments to merchants (not on transfers to other MaestroBank users) — see the per-category rates below.',
  },

  'points.earnRatesTitle': { ro: 'Rate de câștig, pe categorie', en: 'Earn rates, by category' },

  'points.rewardsTitle': { ro: 'Recompense', en: 'Rewards' },
  'points.noBalanceTitle': { ro: 'Niciun sold încă', en: 'No balance yet' },
  'points.noBalanceDesc': {
    ro: 'Fă o plată la un comerciant ca să începi să câștigi puncte.',
    en: 'Make a payment to a merchant to start earning points.',
  },
  'points.redeem': { ro: 'Răscumpără', en: 'Redeem' },

  'points.wheelTitle': { ro: 'Roata norocului', en: 'Wheel of fortune' },
  'points.wheelSubtitle': {
    ro: 'Alege câte puncte pariezi la o învârtire — mai multe puncte pariate înseamnă șanse mai bune la premii mai bune. Punctele pariate se scad imediat, indiferent de rezultat.',
    en: 'Choose how many points to wager on a spin — more points wagered means better odds at better prizes. Wagered points are deducted immediately, regardless of the outcome.',
  },
  'points.pointsWagered': { ro: 'Puncte pariate', en: 'Points wagered' },
  'points.availableBalance': { ro: 'Sold disponibil: {n} puncte', en: 'Available balance: {n} points' },
  'points.spinTheWheel': { ro: 'Rotește roata', en: 'Spin the wheel' },

  'points.redeemModalTitle': { ro: 'Răscumpără {title}', en: 'Redeem {title}' },
  'points.redeemConfirmBefore': { ro: 'Confirmi? Se scad', en: 'Confirm? We deduct' },
  'points.redeemConfirmMiddle': { ro: 'și primești', en: 'and you receive' },
  'points.redeemConfirmAfter': {
    ro: ', creditați direct în contul tău curent.',
    en: ', credited directly to your current account.',
  },
  'points.confirm': { ro: 'Confirmă', en: 'Confirm' },

  'points.spinResultTitle': { ro: 'Rezultatul învârtirii', en: 'Spin result' },
  'points.creditedToAccount': { ro: 'creditați în cont', en: 'credited to your account' },
  'points.betterLuckNextTime': { ro: 'Mai încerci data viitoare.', en: 'Better luck next time.' },
  'points.remainingBalance': { ro: 'Sold rămas: {n} puncte', en: 'Remaining balance: {n} points' },
  'points.gotIt': { ro: 'Am înțeles', en: 'Got it' },

  'points.welcomeBonusToast': { ro: 'Ai primit {n} puncte de bun-venit!', en: 'You received {n} welcome points!' },
  'points.claimFailed': { ro: 'Revendicarea bonusului a eșuat.', en: 'Claiming the bonus failed.' },
  'points.redeemedToast': {
    ro: 'Ai răscumpărat "{title}" — {amount} lei creditați în cont.',
    en: 'You redeemed "{title}" — {amount} RON credited to your account.',
  },
  'points.redeemFailed': { ro: 'Răscumpărarea a eșuat.', en: 'The redemption failed.' },
  'points.spinFailed': { ro: 'Învârtirea a eșuat.', en: 'The spin failed.' },

  // --- Cartea glisabilă "Cum funcționează" (points.ts::HOW_POINTS_WORK_CARDS) ---
  'points.howItWorks.coverTitle': { ro: 'Cum funcționează Punctele MaestroBank', en: 'How MaestroBank Points work' },
  'points.howItWorks.coverText': {
    ro: 'Câștigi, răscumperi sau riști la roată — pe scurt, glisează pentru următorul pas.',
    en: 'Earn, redeem, or risk them on the wheel — in short, swipe for the next step.',
  },
  'points.howItWorks.step1Title': { ro: 'Cumperi de la un comerciant', en: 'You buy from a merchant' },
  'points.howItWorks.step1Text': {
    ro: 'Orice plată către un cont care nu e al altui user MaestroBank îți dă puncte, ca procent din sumă.',
    en: "Any payment to an account that isn't another MaestroBank user's earns you points, as a percentage of the amount.",
  },
  'points.howItWorks.step2Title': { ro: 'Rata diferă pe categorie', en: 'The rate differs by category' },
  'points.howItWorks.step2Text': {
    ro: 'Vezi tabelul de mai jos — de la 0,5% la facturi, până la 3% la restaurante și shopping.',
    en: 'See the table below — from 0.5% on bills up to 3% on restaurants and shopping.',
  },
  'points.howItWorks.step3Title': { ro: 'Le răscumperi pentru cashback', en: 'You redeem them for cashback' },
  'points.howItWorks.step3Text': {
    ro: 'Alegi o recompensă din catalog — banii intră direct în contul tău curent, nu un voucher simulat.',
    en: 'You pick a reward from the catalogue — the money goes straight to your current account, not a simulated voucher.',
  },
  'points.howItWorks.step4Title': { ro: 'Sau le riști la roată', en: 'Or risk them on the wheel' },
  'points.howItWorks.step4Text': {
    ro: 'Pariezi puncte pe o învârtire — mai multe puncte pariate, șanse mai bune la premii mai bune.',
    en: 'You wager points on a spin — more points wagered, better odds at better prizes.',
  },
  'points.howItWorks.benefitWelcomeTitle': { ro: '500 de puncte de bun-venit', en: '500 welcome points' },
  'points.howItWorks.benefitWelcomeText': {
    ro: 'Primești un bonus doar pentru că ești client MaestroBank — revendică-l mai sus, dacă n-ai făcut-o încă.',
    en: "You get a bonus just for being a MaestroBank customer — claim it above if you haven't yet.",
  },
  'points.howItWorks.benefitNoTransfersTitle': { ro: 'Fără puncte pe transferuri', en: 'No points on transfers' },
  'points.howItWorks.benefitNoTransfersText': {
    ro: 'Doar cumpărăturile reale la comercianți dau puncte — nu și banii trimiși prietenilor.',
    en: 'Only real purchases at merchants earn points — not money sent to friends.',
  },
  'points.howItWorks.benefitCashbackTitle': { ro: 'Cashback real', en: 'Real cashback' },
  'points.howItWorks.benefitCashbackText': {
    ro: 'Fiecare recompensă înseamnă bani adevărați în cont, creditați instant.',
    en: 'Every reward means real money in your account, credited instantly.',
  },
  'points.howItWorks.benefitFairTitle': { ro: 'Roata e corectă', en: 'The wheel is fair' },
  'points.howItWorks.benefitFairText': {
    ro: 'Rezultatul se decide pe server ÎNAINTE să vezi roata învârtindu-se — nu poate fi manipulat din browser.',
    en: 'The outcome is decided on the server BEFORE you see the wheel spin — it cannot be manipulated from the browser.',
  },
};
