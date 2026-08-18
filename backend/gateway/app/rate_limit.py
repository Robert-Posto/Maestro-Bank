"""Rate limiting simplu, în memorie, per adresă IP (fereastră glisantă).

IMPORTANT — limitare cunoscută: această implementare ține evidența doar
în memoria procesului curent. E potrivită pentru development / un singur
gateway (MVP). Pentru producție, cu mai multe instanțe de gateway
rulând în paralel (scalare orizontală), fiecare instanță și-ar ține
propria evidență, iar limita reală ar deveni (nr_instanțe * limita
configurată) — pentru asta ar fi nevoie de o soluție distribuită/
persistentă (ex. Redis), intenționat neintrodusă acum.
"""

import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class InMemoryRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        hits = self._hits[client_ip]

        while hits and now - hits[0] > self.window_seconds:
            hits.popleft()

        if len(hits) >= self.max_requests:
            return JSONResponse(
                status_code=429,
                content={"detail": "Prea multe cereri. Încearcă din nou mai târziu."},
            )

        hits.append(now)
        return await call_next(request)
