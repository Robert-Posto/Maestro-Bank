/**
 * Config centralizat pentru URL-ul de bază al API-ului.
 *
 * Flux în development: Angular -> Nginx (localhost:8080) -> API Gateway
 * -> microservicii -> MongoDB. Angular NU vorbește niciodată direct cu
 * microserviciile sau cu Gateway-ul — totul trece prin Nginx.
 *
 * Orice serviciu Angular care are nevoie de URL-ul API-ului trebuie să
 * importe această constantă, nu să-l hardcodeze din nou.
 */
export const API_BASE_URL = 'http://localhost:8080/api';
