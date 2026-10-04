"""arq entrypoint: `arq docagent.worker.main.WorkerSettings`."""

import logging

from arq.connections import RedisSettings

from docagent.engine import Engine
from docagent.settings import get_settings

from .jobs import ingest_document

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


async def startup(ctx: dict) -> None:
    engine = Engine.from_settings(get_settings())
    ctx["engine"] = engine
    logging.getLogger(__name__).info(
        "worker engine ready: vector_backend=%s index_version=%d chunks=%d",
        engine.settings.vector_backend, engine._read_version(), engine.store.count_ready_chunks(),
    )


class WorkerSettings:
    functions = [ingest_document]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_tries = 2
    job_timeout = 600
    max_jobs = 1  # ingestion appends to one on-disk index; Engine.ingest is also locked, this keeps jobs serial
    health_check_interval = 30  # seconds between heartbeats read by `arq --check` (container healthcheck)
