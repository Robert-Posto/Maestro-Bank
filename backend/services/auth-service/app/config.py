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


settings = Settings()
