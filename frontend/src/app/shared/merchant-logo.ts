/**
 * "Logo"-uri de comerciant — vezi UI reference/Transactions.png (Kaufland,
 * Spotify, Zara etc. apar ca insigne pătrate colorate cu inițiala/eticheta
 * brandului, nu poze reale). Aici NU descărcăm sigle reale (fără cerere de
 * rețea, fără risc de marcă înregistrată) — folosim un monogram + culoarea
 * de brand pentru comercianții cunoscuți din scripts/seed_demo_data.py.
 * Comercianții necunoscuți (sau transferurile către alt user MaestroBank)
 * cad pe avatar cu inițiale, vezi shared/components/merchant-avatar.
 */
export interface MerchantBadge {
  label: string;
  bg: string;
  fg: string;
}

const MERCHANT_BADGES: Record<string, MerchantBadge> = {
  // Alimentație
  kaufland: { label: 'K', bg: '#E30613', fg: '#ffffff' },
  lidl: { label: 'L', bg: '#0050AA', fg: '#ffffff' },
  'mega image': { label: 'M', bg: '#E4032E', fg: '#ffffff' },
  carrefour: { label: 'C', bg: '#004E9E', fg: '#ffffff' },

  // Shopping
  zara: { label: 'ZARA', bg: '#111111', fg: '#ffffff' },
  'h&m': { label: 'H&M', bg: '#E50010', fg: '#ffffff' },
  sephora: { label: 'S', bg: '#111111', fg: '#ffffff' },
  emag: { label: 'eM', bg: '#1A9BDA', fg: '#ffffff' },
  altex: { label: 'A', bg: '#E4032E', fg: '#ffffff' },
  notino: { label: 'N', bg: '#DA1884', fg: '#ffffff' },

  // Transport
  uber: { label: 'U', bg: '#111111', fg: '#ffffff' },
  bolt: { label: 'B', bg: '#34D186', fg: '#0a2e1c' },
  'bolt food': { label: 'B', bg: '#34D186', fg: '#0a2e1c' },
  omv: { label: 'OMV', bg: '#003DA5', fg: '#ffffff' },
  metrorex: { label: 'M', bg: '#003DA5', fg: '#ffffff' },

  // Restaurante
  starbucks: { label: 'S', bg: '#00704A', fg: '#ffffff' },
  "mcdonald's": { label: 'M', bg: '#FFC72C', fg: '#5a3200' },
  'la mama': { label: 'LM', bg: '#7B4B2A', fg: '#ffffff' },
  glovo: { label: 'G', bg: '#FFC244', fg: '#3a2200' },
  'trattoria roma': { label: 'TR', bg: '#7B4B2A', fg: '#ffffff' },
  'casa boierească': { label: 'CB', bg: '#7B4B2A', fg: '#ffffff' },

  // Facturi / utilități
  electrica: { label: 'E', bg: '#FDB813', fg: '#3a2b00' },
  engie: { label: 'E', bg: '#5FC9F3', fg: '#003a5c' },
  digi: { label: 'D', bg: '#EA5B0C', fg: '#ffffff' },
  vodafone: { label: 'V', bg: '#E60000', fg: '#ffffff' },
  orange: { label: 'O', bg: '#FF7900', fg: '#ffffff' },

  // Entertainment / abonamente
  netflix: { label: 'N', bg: '#E50914', fg: '#ffffff' },
  spotify: { label: 'S', bg: '#1DB954', fg: '#ffffff' },
  icloud: { label: 'iC', bg: '#3693F3', fg: '#ffffff' },
  'cinema city': { label: 'CC', bg: '#E4032E', fg: '#ffffff' },
  eventim: { label: 'E', bg: '#E2001A', fg: '#ffffff' },
  steam: { label: 'S', bg: '#171A21', fg: '#ffffff' },

  // Altele
  'dr. max': { label: 'Dr', bg: '#00A651', fg: '#ffffff' },
  'bebe tei': { label: 'BT', bg: '#F06292', fg: '#ffffff' },
  'booking.com': { label: 'B', bg: '#003580', fg: '#ffffff' },

  // Venituri
  salariu: { label: '€', bg: '#16A34A', fg: '#ffffff' },
};

/** Caută insigna de brand pentru un nume de comerciant (case-insensitive). Null dacă nu-l cunoaștem. */
export function merchantBadge(name: string | null | undefined): MerchantBadge | null {
  if (!name) return null;
  return MERCHANT_BADGES[name.trim().toLowerCase()] ?? null;
}
