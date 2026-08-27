"""Loop intern, în-proces — verifică depozitele scadente și le reînnoiește/
plătește. Vezi app/service.py::process_matured_deposits. Același tipar ca
transactions-service/app/scheduler.py (asyncio.Task, pornit/oprit din
app/main.py::lifespan) — nu RabbitMQ/Celery, suficient pt un demo cu un
singur worker."""

import asyncio
import logging

from app.config import settings
from app.service import process_matured_deposits

logger = logging.getLogger("deposits-service")


async def maturity_loop() -> None:
    while True:
        try:
            processed = await process_matured_deposits()
            if processed:
                logger.info("deposits-service: %s depozit(e) procesate la scadență", processed)
        except Exception:
            logger.exception("deposits-service: eroare în loop-ul de scadență")
        await asyncio.sleep(settings.maturity_poll_seconds)
