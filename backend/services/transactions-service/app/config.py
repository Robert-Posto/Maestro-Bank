import os


class Settings:
    mongo_url: str = os.getenv("MONGO_URL", "mongodb://localhost:27017/tx_db")
    jwt_secret: str = os.getenv("JWT_SECRET", "change-me-in-development")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")

    # Adrese INTERNE Docker — transactions-service NU citește niciodată
    # direct accounts_db/budgets_db; orice info despre conturi/abonamente
    # vine prin API-ul serviciului responsabil.
    accounts_service_url: str = os.getenv("ACCOUNTS_SERVICE_URL", "http://accounts-service:8000")
    budgets_service_url: str = os.getenv("BUDGETS_SERVICE_URL", "http://budgets-service:8000")
    auth_service_url: str = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8000")
    support_service_url: str = os.getenv("SUPPORT_SERVICE_URL", "http://support-service:8000")

    # Cât de des verificăm dacă există transferuri programate scadente —
    # vezi app/scheduler.py. 60s e suficient de responsiv pentru un demo
    # (userul nu așteaptă ore ca să vadă un transfer "acum" executat).
    scheduled_transfers_poll_seconds: int = int(os.getenv("SCHEDULED_TRANSFERS_POLL_SECONDS", "60"))

    # Motorul de scoring fraud (vezi app/fraud/). Comutator operațional:
    # cod nou, netestat în producție, care acum atinge FIECARE transfer —
    # permite dezactivarea lui fără deploy dacă se dovedește instabil.
    fraud_engine_enabled: bool = os.getenv("FRAUD_ENGINE_ENABLED", "true").lower() == "true"
    fraud_cohort_baseline_ttl_hours: int = int(os.getenv("FRAUD_COHORT_BASELINE_TTL_HOURS", "24"))
    # False = aplicare REALĂ la banda "hold" (80+): transferul e reținut,
    # nu doar logat — vezi app/holds.py. True = comportamentul din Faza 1
    # (evaluează, loghează, NU blochează niciodată nimic). Comutator
    # separat de fraud_engine_enabled — ăsta controlează DOAR dacă banda
    # calculată ajunge să conteze, nu dacă evaluarea rulează deloc.
    fraud_shadow_mode: bool = os.getenv("FRAUD_SHADOW_MODE", "false").lower() == "true"

    # Reținerile (holds) expirate (>24h nerezolvate) sunt inversate automat
    # de un loop intern — vezi app/scheduler.py::hold_expiry_loop. Interval
    # de verificare, NU durata reținerii (aceea e hold.expires_at, per
    # document, comparat cu evaluated_at-ul transferului).
    hold_sweep_poll_seconds: int = int(os.getenv("HOLD_SWEEP_POLL_SECONDS", "60"))
    hold_ttl_hours: int = int(os.getenv("HOLD_TTL_HOURS", "24"))


settings = Settings()
