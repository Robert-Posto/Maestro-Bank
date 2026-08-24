/**
 * Decodare CLIENT-SIDE a payload-ului JWT, DOAR pentru afișare (ex.
 * "sesiune expiră la ora X") — NU e folosită niciodată pentru
 * autorizare (aceea rămâne strict responsabilitatea backendului, care
 * validează semnătura). Un JWT decodat fără verificare de semnătură nu
 * e o sursă de adevăr pentru securitate.
 */
export interface DecodedJwtPayload {
  sub?: string;
  email?: string;
  role?: 'customer' | 'staff';
  iat?: number;
  exp?: number;
}

export function decodeJwtPayload(token: string): DecodedJwtPayload | null {
  try {
    const [, payloadSegment] = token.split('.');
    if (!payloadSegment) return null;
    const normalized = payloadSegment.replace(/-/g, '+').replace(/_/g, '/');
    const json = atob(normalized.padEnd(normalized.length + ((4 - (normalized.length % 4)) % 4), '='));
    return JSON.parse(json);
  } catch {
    return null;
  }
}
