"""Loop-uri interne, în-proces — transferuri programate + expirarea
hold-urilor de fraud.

NU e RabbitMQ/Celery — câte un `asyncio.Task` per loop, pornite la startup
(vezi app/main.py::lifespan) și oprite la shutdown. Suficient pentru un
demo cu un singur worker per serviciu; dacă transactions-service ar rula
vreodată cu mai multe replici, ar trebui înlocuit cu un lock distribuit sau
o coadă reală, ca să nu execute același transfer/aceeași rezolvare de hold
de mai multe ori (sweep_expired_holds e deja idempotent prin construcție —
vezi app/holds.py — dar dublarea EFORTULUI, nu a EFECTULUI, tot ar rămâne).
"""

import asyncio
import logging

from app.config import settings
from app.holds import sweep_expired_holds
from app.service import run_due_scheduled_transfers

logger = logging.getLogger("transactions-service")


async def scheduled_transfers_loop() -> None:
    while True:
        try:
            await run_due_scheduled_transfers()
        except Exception:
            logger.exception("transactions-service: eroare în loop-ul de transferuri programate")
        await asyncio.sleep(settings.scheduled_transfers_poll_seconds)


async def hold_expiry_loop() -> None:
    """Atinge bani reali (inversează hold-uri expirate) — de-aia
    main.py::lifespan îl oprește cu grijă (task.cancel() + await, nu doar
    fire-and-forget ca la scheduled_transfers_loop), ca un shutdown să nu
    întrerupă o rezolvare la jumătate."""
    while True:
        try:
            processed = await sweep_expired_holds()
            if processed:
                logger.info("transactions-service: sweep hold-uri expirate — %s rezolvate", processed)
        except Exception:
            logger.exception("transactions-service: eroare în loop-ul de expirare hold-uri")
        await asyncio.sleep(settings.hold_sweep_poll_seconds)
