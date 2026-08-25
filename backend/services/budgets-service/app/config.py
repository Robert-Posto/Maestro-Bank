import os


class Settings:
    mongo_url: str = os.getenv("MONGO_URL", "mongodb://localhost:27017/budgets_db")
    jwt_secret: str = os.getenv("JWT_SECRET", "change-me-in-development")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    # Adresă INTERNĂ Docker — folosită DOAR pentru detecția pasivă de
    # abonamente (vezi service.py::detect_recurring_payments), care citește
    # istoricul de tranzacții al userului ca să găsească plăți recurente.
    transactions_service_url: str = os.getenv("TRANSACTIONS_SERVICE_URL", "http://transactions-service:8000")


settings = Settings()
