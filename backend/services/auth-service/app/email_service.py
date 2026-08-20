"""Trimitere email de verificare, prin SMTP (stdlib — fără dependință nouă).

Dacă SMTP_HOST nu e configurat (implicit, în development), codul NU se
trimite pe mail — e doar logat, ca să poți testa fluxul complet fără un
cont de email real. Vezi app/config.py pentru variabilele de mediu.
"""

import logging
import smtplib
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger("auth-service")


def send_verification_email(to_email: str, first_name: str, code: str) -> None:
    if not settings.smtp_host:
        logger.info(
            "auth-service: SMTP_HOST nu e configurat — codul de verificare pentru %s este: %s "
            "(setează SMTP_HOST/SMTP_USER/SMTP_PASSWORD în .env ca să trimiți email real)",
            to_email,
            code,
        )
        return

    message = EmailMessage()
    message["Subject"] = "Codul tău de verificare MaestroBank"
    message["From"] = settings.smtp_from
    message["To"] = to_email
    message.set_content(
        f"Salut, {first_name}!\n\n"
        f"Codul tău de verificare este: {code}\n\n"
        f"Codul expiră în {settings.email_verification_code_ttl_minutes} minute. "
        "Dacă nu ai cerut acest cod, poți ignora acest email.\n\n"
        "— Echipa MaestroBank"
    )

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)
        logger.info("auth-service: email de verificare trimis către %s", to_email)
    except Exception:
        # Nu blocăm fluxul de register/resend dacă SMTP-ul pică — userul
        # poate cere reîncercare din UI ("Retrimite codul"). Logăm codul
        # aici și în caz de EȘEC (nu doar când SMTP_HOST lipsește) — altfel,
        # cu SMTP configurat dar inaccesibil (ex. rețea care blochează
        # portul), userul rămâne fără nicio cale să vadă codul.
        logger.exception(
            "auth-service: trimiterea emailului de verificare către %s a eșuat — codul este: %s",
            to_email,
            code,
        )
