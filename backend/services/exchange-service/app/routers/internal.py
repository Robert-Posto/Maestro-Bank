"""Rute INTERNE (service-to-service) — orice path care începe cu
"internal/" e blocat la Gateway, indiferent de autentificare (vezi
backend/gateway/app/routers/proxy.py::_forward). Userul din path e primit
ca parametru de încredere — apelantul (alt serviciu backend, nu browserul)
l-a rezolvat deja dintr-un JWT valid.

Folosit de transactions-service pentru extrasul de cont (vezi
transactions-service/app/service.py::generate_account_statement) — un cont
EUR/USD/GBP (sau chiar contul curent RON, pentru latura RON a unui schimb)
se poate alimenta/debita prin schimb valutar, nu doar prin transfer IBAN;
mișcările astea NU apar niciodată în tx_db (transactions-service), care
știe doar de transferuri.
"""

from fastapi import APIRouter

from app.models import ExchangeOut
from app.service import list_exchanges_for_user

router = APIRouter(prefix="/internal/exchanges", tags=["internal"])


@router.get("/by-user/{user_id}", response_model=list[ExchangeOut], response_model_by_alias=False)
async def get_exchanges_by_user(user_id: str):
    return await list_exchanges_for_user(user_id)
