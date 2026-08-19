"""Rute INTERNE ale auth-service — DOAR service-to-service.

Apelabile de alte microservicii (ex. transactions-service, ca să afișeze
numele contrapărții la un transfer), folosind adresa internă Docker
(`http://auth-service:8000`). NU sunt expuse prin API Gateway — gateway
blochează explicit orice path care începe cu "internal/" (vezi
backend/gateway/app/routers/proxy.py), deci nu sunt accesibile din
browser/Angular.
"""

from fastapi import APIRouter

from app import service
from app.models import InternalUserNameView

router = APIRouter(prefix="/internal/users", tags=["internal"])


@router.get("/{user_id}", response_model=InternalUserNameView)
async def get_user_name(user_id: str):
    return await service.get_user_name(user_id)
