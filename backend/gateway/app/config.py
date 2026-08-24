"""Configurație citită din variabile de mediu. Nimic hardcodat aici."""

import os


class Settings:
    mongo_url: str = os.getenv("MONGO_URL", "mongodb://localhost:27017")

    jwt_secret: str = os.getenv("JWT_SECRET", "change-me-in-development")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")

    # Adrese INTERNE Docker Compose — NU localhost. Browserul nu le
    # accesează niciodată direct, doar containerul gateway.
    auth_service_url: str = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8000")
    accounts_service_url: str = os.getenv("ACCOUNTS_SERVICE_URL", "http://accounts-service:8000")
    transactions_service_url: str = os.getenv("TRANSACTIONS_SERVICE_URL", "http://transactions-service:8000")
    budgets_service_url: str = os.getenv("BUDGETS_SERVICE_URL", "http://budgets-service:8000")
    support_service_url: str = os.getenv("SUPPORT_SERVICE_URL", "http://support-service:8000")
    exchange_service_url: str = os.getenv("EXCHANGE_SERVICE_URL", "http://exchange-service:8000")
    verification_service_url: str = os.getenv("VERIFICATION_SERVICE_URL", "http://verification-service:8000")
    ai_service_url: str = os.getenv("AI_SERVICE_URL", "http://ai-orchestrator-service:8000")

    cors_allowed_origins: list[str] = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ALLOWED_ORIGINS",
            "http://localhost:4200,http://localhost:8080",
        ).split(",")
        if origin.strip()
    ]

    rate_limit_max_requests: int = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "300"))
    rate_limit_window_seconds: int = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))


settings = Settings()
