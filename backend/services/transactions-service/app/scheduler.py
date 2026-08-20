"""Loop intern, în-proces, pentru transferurile programate.

NU e RabbitMQ/Celery — un singur `asyncio.Task`, pornit la startup (vezi
app/main.py::lifespan) și oprit la shutdown. Suficient pentru un demo cu
un singur worker per serviciu; dacă transactions-service ar rula vreodată
cu mai multe replici, ar trebui înlocuit cu un lock distribuit sau o coadă
reală, ca să nu execute același transfer de mai multe ori.
"""

import asyncio
import logging

from app.config import settings
from app.service import run_due_scheduled_transfers

logger = logging.getLogger("transactions-service")


async def scheduled_transfers_loop() -> None:
    while True:
        try:
            await run_due_scheduled_transfers()
        except Exception:
            logger.exception("transactions-service: eroare în loop-ul de transferuri programate")
        await asyncio.sleep(settings.scheduled_transfers_poll_seconds)
