"""Configurație pentru points-service.

Ratele de câștig, catalogul de recompense și segmentele roții sunt politică
PROPRIE MaestroBank (vezi app/earn_rates.py, app/rewards_catalog.py,
app/wheel_segments.py) — nu un feed extern, la fel ca ratele de depozit.
"""

import os


class Settings:
    mongo_url: str = os.getenv("MONGO_URL", "mongodb://localhost:27017/points_db")
    jwt_secret: str = os.getenv("JWT_SECRET", "change-me-in-development")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")

    # Adresă INTERNĂ Docker — răscumpărarea unei recompense sau un câștig la
    # roată cer accounts-service să crediteze efectiv contul curent al
    # userului (vezi /internal/accounts/{id}/credit, NEexpus prin Gateway,
    # deja reutilizat identic de deposits-service/investments-service).
    accounts_service_url: str = os.getenv("ACCOUNTS_SERVICE_URL", "http://accounts-service:8000")

    # Notificare la răscumpărare recompensă / câștig la roată (best-effort,
    # NU și la fiecare câștig de puncte — ar spama, decizie confirmată în
    # design). Vezi app/service.py::_notify_user.
    support_service_url: str = os.getenv("SUPPORT_SERVICE_URL", "http://support-service:8000")


settings = Settings()
