"""verification-service — verificare identitate (buletin vs. selfie, prin
DeepFace). Serviciu STATELESS: nu are bază de date proprie, nu persistă
imagini — vezi app/service.py pentru motiv. Rezultatul verificării ajunge
DOAR ca flag pe user-ul din auth_db (identity_verified), prin apel intern.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import service
from app.i18n import LanguageMiddleware
from app.routers.verification import router as verification_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [verification-service] %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Serviciul nu începe să accepte cereri (nici /health) până nu termină
    # asta — vezi service.py::warm_up_model pentru motiv (evită un 504 la
    # Gateway pe PRIMA cerere reală din viața containerului).
    await service.warm_up_model()
    yield


app = FastAPI(title="MaestroBank Verification Service", lifespan=lifespan)
app.add_middleware(LanguageMiddleware)
app.include_router(verification_router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "verification-service"}
