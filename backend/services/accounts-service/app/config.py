import os


class Settings:
    mongo_url: str = os.getenv("MONGO_URL", "mongodb://localhost:27017/accounts_db")
    jwt_secret: str = os.getenv("JWT_SECRET", "change-me-in-development")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")

    # Adresă INTERNĂ Docker — folosită DOAR pentru a verifica parola userului
    # curent înainte de a dezvălui PAN/CVV la un card (vezi
    # app/service.py::reveal_card). NU e o dependență de pornire (nu apare
    # în depends_on din docker-compose.yml): auth-service depinde deja de
    # accounts-service la pornire, iar o dependență în ambele sensuri ar
    # crea un ciclu pe care Docker Compose nu-l permite. Apelul runtime
    # funcționează oricum, atâta timp cât auth-service e sus până când un
    # user chiar cere reveal — ceea ce se întâmplă mult după ce tot stack-ul
    # a pornit.
    auth_service_url: str = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8000")


settings = Settings()
