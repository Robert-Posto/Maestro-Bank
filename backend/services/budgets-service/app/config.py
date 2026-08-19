import os


class Settings:
    mongo_url: str = os.getenv("MONGO_URL", "mongodb://localhost:27017/budgets_db")
    jwt_secret: str = os.getenv("JWT_SECRET", "change-me-in-development")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")


settings = Settings()
