"""arq entrypoint: `arq docagent.worker.main.WorkerSettings`."""

import logging

from arq.connections import RedisSettings

from docagent.engine import Engine
from docagent.settings import get_settings

from .jobs import ingest_document

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


async def startup(ctx: dict) -> None:
    ctx["engine"] = Engine.from_settings(get_settings())


class WorkerSettings:
    functions = [ingest_document]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_tries = 2
    job_timeout = 600
    health_check_interval = 30  # seconds between heartbeats read by `arq --check` (container healthcheck)
