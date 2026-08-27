"""Loop intern, în-proces — reîmprospătează cache-ul de prețuri periodic.
Vezi app/prices.py::refresh_all_prices. Același tipar ca exchange-service/
app/main.py::_rates_refresh_loop (asyncio.Task, pornit/oprit din
app/main.py::lifespan) — nu RabbitMQ/Celery, suficient pt un demo cu un
singur worker.
"""

import asyncio
import logging

from app.catalog import SYMBOLS
from app.config import settings
from app.prices import refresh_all_prices

logger = logging.getLogger("investments-service")


async def price_refresh_loop() -> None:
    while True:
        try:
            updated = await refresh_all_prices()
            logger.info("investments-service: prețuri reîmprospătate (%s/%s simboluri)", updated, len(SYMBOLS))
        except Exception:
            logger.exception("investments-service: eroare în loop-ul de reîmprospătare prețuri")
        await asyncio.sleep(settings.price_refresh_interval_seconds)
