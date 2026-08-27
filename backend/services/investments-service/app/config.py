"""Configurație pentru investments-service.

Vezi docs/superpowers/specs/2026-08-27-investments-design.md — spre
deosebire de exchange-service (feed BNR OFICIAL), prețurile de aici vin de
la un endpoint NEOFICIAL Yahoo Finance (nu există un echivalent gratuit,
fără cheie, oficial pentru cotații bursiere live) — vezi app/prices.py
pentru detalii și fallback.
"""

import os


class Settings:
    mongo_url: str = os.getenv("MONGO_URL", "mongodb://localhost:27017/investments_db")
    jwt_secret: str = os.getenv("JWT_SECRET", "change-me-in-development")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")

    # Adresă INTERNĂ Docker — cumpărarea/vânzarea cere accounts-service să
    # debiteze/crediteze efectiv contul USD al userului (vezi
    # /internal/accounts/{id}/debit și /credit — primitive GENERICE,
    # construite deja pentru deposits-service, reutilizate identic aici).
    accounts_service_url: str = os.getenv("ACCOUNTS_SERVICE_URL", "http://accounts-service:8000")

    # Cât de des reîmprospătăm cache-ul de prețuri (16 simboluri) de la
    # Yahoo — piața se mișcă mult mai rapid decât cursul valutar (BNR, 6h),
    # dar tot nu are sens să batem endpoint-ul neoficial la fiecare cerere.
    price_refresh_interval_seconds: int = int(os.getenv("PRICE_REFRESH_INTERVAL_SECONDS", str(15 * 60)))


settings = Settings()
