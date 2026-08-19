/**
 * Extrage un mesaj de eroare afișabil dintr-un răspuns HTTP FastAPI.
 *
 * FastAPI întoarce `{"detail": "mesaj"}` pentru erori de business (4xx
 * "normale") și `{"detail": [{msg, loc, type, ...}, ...]}` pentru erori
 * de validare Pydantic (422) — le tratăm pe amândouă aici, într-un
 * singur loc, în loc să reinventăm parsarea în fiecare componentă.
 */
export function extractErrorMessage(err: unknown, fallback: string): string {
  const detail = (err as { error?: { detail?: unknown } })?.error?.detail;

  if (typeof detail === 'string') {
    return detail;
  }

  if (Array.isArray(detail) && detail.length > 0) {
    const messages = detail
      .map((issue) => (issue && typeof issue === 'object' ? (issue as { msg?: string }).msg : null))
      .filter((msg): msg is string => typeof msg === 'string' && msg.length > 0)
      .map((msg) => msg.replace(/^Value error,\s*/, ''));

    if (messages.length > 0) {
      return messages.join(' ');
    }
  }

  return fallback;
}
