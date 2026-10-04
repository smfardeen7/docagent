import asyncio
import logging

log = logging.getLogger(__name__)


async def ingest_document(ctx: dict, doc_id: str) -> int:
    """arq job: embed and index one uploaded document. CPU-bound, so it runs off the event loop."""
    engine = ctx["engine"]
    n = await asyncio.to_thread(engine.ingest, doc_id)
    log.info("job ingest_document %s -> %d chunks", doc_id, n)
    return n
