"""uvicorn entrypoint: `uvicorn docagent.api.main:app`."""

import logging

from arq import create_pool
from arq.connections import RedisSettings

from docagent.engine import Engine
from docagent.settings import get_settings

from .app import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
settings = get_settings()
engine = Engine.from_settings(settings)
_pool = None


async def enqueue(doc_id: str) -> None:
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    await _pool.enqueue_job("ingest_document", doc_id)


app = create_app(engine, enqueue)
