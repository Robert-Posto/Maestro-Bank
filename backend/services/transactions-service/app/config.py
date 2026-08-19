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


settings = Settings()
