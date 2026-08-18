"""API Gateway — singurul punct prin care Angular vorbește cu backendul.

Responsabilități:
  * routing / forwarding către microservicii (vezi routers/proxy.py);
  * validare JWT pentru rutele protejate (vezi security.py);
  * CORS (doar origin-urile de development, nu "*");
  * rate limiting simplu, în memorie (vezi rate_limit.py);
  * status agregat al arhitecturii (vezi routers/system.py).
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.rate_limit import InMemoryRateLimitMiddleware
from app.routers.proxy import router as proxy_router
from app.routers.system import router as system_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [gateway] %(levelname)s %(message)s")
logger = logging.getLogger("gateway")

app = FastAPI(title="MaestroBank API Gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    InMemoryRateLimitMiddleware,
    max_requests=settings.rate_limit_max_requests,
    window_seconds=settings.rate_limit_window_seconds,
)

# Rutele specifice (ex. /api/auth/me) trebuie înregistrate ÎNAINTE de
# catch-all-ul /api/{service}/{path:path} din proxy_router, altfel
# catch-all-ul le-ar prinde pe el primul.
app.include_router(system_router)
app.include_router(proxy_router)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "gateway"}
