/**
 * Chei `sessionStorage` folosite de mai multe module — un singur loc de
 * adevăr, ca să nu apară același literal duplicat (risc de drift) în
 * feature-ul care scrie (ex. features/support/support.ts) și în cel care
 * curăță la logout (services/auth.service.ts).
 */

/** Transcriptul conversației cu Support Agent (vezi features/support/support.ts)
 * — persistat în `sessionStorage` (ca și JWT-ul, vezi AuthService), NU
 * `localStorage`: dispare la închiderea tab-ului/browserului, nu rămâne pe
 * disc la nesfârșit. Șters explicit la logout (vezi AuthService.logout()),
 * ca userul următor de pe același tab să nu vadă conversația celui dinainte. */
export const SUPPORT_CHAT_STORAGE_KEY = 'maestrobank_support_chat_v1';
