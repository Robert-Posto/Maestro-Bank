"""Configurație pentru deposits-service.

Vezi docs/superpowers/specs/2026-08-27-deposits-design.md — ratele sunt
politică PROPRIE MaestroBank (app/rates.py), NU un feed extern (spre
deosebire de exchange-service/app/bnr_rates.py, care ia cursul FX real,
zilnic, de la BNR).
"""

import os


class Settings:
    mongo_url: str = os.getenv("MONGO_URL", "mongodb://localhost:27017/deposits_db")
    jwt_secret: str = os.getenv("JWT_SECRET", "change-me-in-development")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")

    # Adresă INTERNĂ Docker — deschiderea/lichidarea unui depozit cere
    # accounts-service să debiteze/crediteze efectiv contul userului (vezi
    # /internal/accounts/{id}/debit și /credit, NEexpuse prin Gateway).
    accounts_service_url: str = os.getenv("ACCOUNTS_SERVICE_URL", "http://accounts-service:8000")

    # Cât de des verificăm dacă există depozite scadente — vezi
    # app/scheduler.py::maturity_loop. 60s e suficient de responsiv pt un
    # demo (userul nu așteaptă ore ca să vadă reînnoirea/plata "acum").
    maturity_poll_seconds: int = int(os.getenv("MATURITY_POLL_SECONDS", "60"))


settings = Settings()
