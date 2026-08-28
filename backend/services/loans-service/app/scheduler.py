"""Loop intern, în-proces — verifică ratele scadente și le debitează. Vezi
app/service.py::process_due_payments. Același tipar ca
deposits-service/app/scheduler.py (asyncio.Task, pornit/oprit din
app/main.py::lifespan) — nu RabbitMQ/Celery, suficient pt un demo cu un
singur worker.
"""

import asyncio
import logging

from app.config import settings
from app.service import process_due_payments

logger = logging.getLogger("loans-service")


async def payment_due_loop() -> None:
    while True:
        try:
            processed = await process_due_payments()
            if processed:
                logger.info("loans-service: %s rată/rate procesată(e)", processed)
        except Exception:
            logger.exception("loans-service: eroare în loop-ul de rate scadente")
        await asyncio.sleep(settings.payment_poll_seconds)
