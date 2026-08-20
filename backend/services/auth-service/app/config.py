"""Configurație citită din variabile de mediu. Nimic hardcodat aici."""

import os


class Settings:
    mongo_url: str = os.getenv("MONGO_URL", "mongodb://localhost:27017/auth_db")
    jwt_secret: str = os.getenv("JWT_SECRET", "change-me-in-development")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    jwt_expires_minutes: int = int(os.getenv("JWT_EXPIRES_MINUTES", "60"))

    # Adresă INTERNĂ Docker — folosită pentru a proviziona automat contul
    # bancar + cardul virtual al unui user nou, imediat după register.
    accounts_service_url: str = os.getenv("ACCOUNTS_SERVICE_URL", "http://accounts-service:8000")

    # --- WebAuthn / passkeys ------------------------------------------
    # rp_id = domeniul "gol" (fără schemă/port) al originii unde rulează
    # efectiv Angular în browser. În acest setup de development, Angular
    # (ng serve) e servit direct pe :4200 — Nginx pe :8080 e DOAR un proxy
    # de API, browserul nu navighează niciodată acolo — deci rp_id="localhost"
    # + originea "http://localhost:4200" sunt valorile corecte, NU :8080.
    webauthn_rp_id: str = os.getenv("WEBAUTHN_RP_ID", "localhost")
    webauthn_rp_name: str = os.getenv("WEBAUTHN_RP_NAME", "MaestroBank")
    webauthn_origins: list[str] = [
        origin.strip() for origin in os.getenv("WEBAUTHN_ORIGINS", "http://localhost:4200").split(",") if origin.strip()
    ]
    webauthn_challenge_ttl_seconds: int = int(os.getenv("WEBAUTHN_CHALLENGE_TTL_SECONDS", "120"))


settings = Settings()
