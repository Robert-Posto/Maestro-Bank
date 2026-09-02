"""Configurație pentru loans-service.

Dobânda anuală și pragul de eligibilitate (app/rates.py, app/eligibility.py)
sunt politică PROPRIE MaestroBank — nu un feed extern, la fel ca ratele de
depozit (nici băncile reale nu iau rata unui credit de consum dintr-o piață
publică, e stabilită intern, pe bază de risc).
"""

import os


class Settings:
    mongo_url: str = os.getenv("MONGO_URL", "mongodb://localhost:27017/loans_db")
    jwt_secret: str = os.getenv("JWT_SECRET", "change-me-in-development")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")

    # Adresă INTERNĂ Docker — aprobarea/rata/plata anticipată cer
    # accounts-service să crediteze/debiteze efectiv contul curent (vezi
    # /internal/accounts/{id}/credit și /debit, NEexpuse prin Gateway,
    # deja reutilizate identic de deposits-service/investments-service).
    accounts_service_url: str = os.getenv("ACCOUNTS_SERVICE_URL", "http://accounts-service:8000")

    # Adresă INTERNĂ Docker — verificarea de eligibilitate trage istoricul
    # REAL de tranzacții al userului (vezi /internal/transactions/by-user/{id},
    # deja reutilizat de budgets-service::detect_recurring_payments, același
    # tipar: pull, nu push).
    transactions_service_url: str = os.getenv("TRANSACTIONS_SERVICE_URL", "http://transactions-service:8000")

    # Notificare la aprobare/respingere/plată/plată ratată/închidere credit.
    support_service_url: str = os.getenv("SUPPORT_SERVICE_URL", "http://support-service:8000")

    # Adresă INTERNĂ Docker — datele de contact ale aplicantului, pentru
    # ecranul de personal (vezi app/routers/staff.py) — identic ca tipar cu
    # transactions-service/app/holds.py::_fetch_user_contact.
    auth_service_url: str = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8000")

    # Cât de des verificăm dacă există rate scadente — vezi
    # app/scheduler.py::payment_due_loop. 60s e suficient de responsiv pt
    # un demo, la fel ca la maturity_loop de la Depozite.
    payment_poll_seconds: int = int(os.getenv("LOAN_PAYMENT_POLL_SECONDS", "60"))


settings = Settings()
