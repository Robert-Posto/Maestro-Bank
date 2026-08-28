import { TranslationEntry } from './index';

export const PAY_REQUEST_I18N: Record<string, TranslationEntry> = {
  'payRequest.title': { ro: 'Cerere de plată', en: 'Payment request' },
  'payRequest.subtitle': {
    ro: 'Cineva ți-a trimis acest link ca să-i plătești o sumă fixă.',
    en: 'Someone sent you this link to pay them a fixed amount.',
  },

  'payRequest.notFoundTitle': { ro: 'Cerere de plată inexistentă', en: 'Payment request not found' },
  'payRequest.notFoundDesc': {
    ro: 'Link-ul e greșit sau cererea a fost ștearsă. Verifică-l cu persoana care ți l-a trimis.',
    en: 'The link is wrong or the request was deleted. Check it with the person who sent it to you.',
  },
  'payRequest.backToAccount': { ro: '‹ Înapoi la cont', en: '‹ Back to account' },

  'payRequest.paymentDone': { ro: 'Plată efectuată', en: 'Payment completed' },
  'payRequest.towards': { ro: 'către', en: 'to' },
  'payRequest.viewInTransactions': { ro: 'Vezi în tranzacții ›', en: 'View in transactions ›' },

  'payRequest.statusOpen': { ro: 'Deschisă', en: 'Open' },
  'payRequest.statusPaid': { ro: 'Plătită', en: 'Paid' },
  'payRequest.statusCancelled': { ro: 'Anulată', en: 'Cancelled' },
  'payRequest.statusExpired': { ro: 'Expirată', en: 'Expired' },

  'payRequest.alreadyPaid': { ro: 'Această cerere a fost deja plătită', en: 'This request has already been paid' },
  'payRequest.by': { ro: 'de', en: 'by' },
  'payRequest.cancelledByPrefix': { ro: 'Această cerere a fost anulată de', en: 'This request was cancelled by' },
  'payRequest.requester': { ro: 'solicitant', en: 'the requester' },
  'payRequest.expiredMessage': {
    ro: 'Link-ul a expirat — cere-i persoanei să genereze unul nou.',
    en: 'The link has expired — ask the person to generate a new one.',
  },

  'payRequest.ownRequestBadge': { ro: 'Aceasta este cererea ta', en: 'This is your request' },
  'payRequest.ownRequestHintPrefix': {
    ro: 'Nu poți plăti propria cerere — trimite link-ul altcuiva, sau gestionează-ți cererile din',
    en: 'You cannot pay your own request — send the link to someone else, or manage your requests from',
  },
  'payRequest.cancelRequestBtn': { ro: 'Anulează cererea', en: 'Cancel request' },
  'payRequest.viewAllMyRequests': { ro: 'Vezi toate cererile mele ›', en: 'View all my requests ›' },

  'payRequest.aMaestroBankUser': { ro: 'Un user MaestroBank', en: 'A MaestroBank user' },
  'payRequest.requestsAPayment': { ro: 'îți cere o plată', en: 'is requesting a payment from you' },
  'payRequest.payButtonPrefix': { ro: 'Plătește', en: 'Pay' },
  'payRequest.disclaimer': {
    ro: 'Suma e fixă, stabilită de solicitant — plata se face din contul tău curent MaestroBank.',
    en: 'The amount is fixed, set by the requester — payment is made from your MaestroBank current account.',
  },

  'payRequest.paymentSuccessToast': { ro: 'Plată efectuată cu succes.', en: 'Payment completed successfully.' },
  'payRequest.requestCancelledToast': { ro: 'Cerere de plată anulată.', en: 'Payment request cancelled.' },
  'payRequest.cancelError': { ro: 'Anularea a eșuat.', en: 'Cancellation failed.' },
  'payRequest.transferServiceUnavailable': {
    ro: 'Serviciul de transferuri este indisponibil momentan. Încearcă din nou.',
    en: 'The transfers service is temporarily unavailable. Try again.',
  },
  'payRequest.requestNoLongerActive': {
    ro: 'Această cerere de plată nu mai este activă (a fost plătită, anulată sau a expirat).',
    en: 'This payment request is no longer active (it was paid, cancelled, or has expired).',
  },
  'payRequest.paymentFailedGeneric': {
    ro: 'Plata a eșuat. Verifică soldul și încearcă din nou.',
    en: 'Payment failed. Check your balance and try again.',
  },
};
