from docagent.engine import Engine
from docagent.index import HashEmbedder
from docagent.llm import FakeProvider
from docagent.retrieve import LexicalReranker
from docagent.settings import Settings
from docagent.worker.jobs import ingest_document
from docagent.worker.main import WorkerSettings


async def test_ingest_job_uses_engine_from_ctx(tmp_path):
    s = Settings(data_dir=tmp_path, provider="fake", vector_backend="numpy", chunk_tokens=32, chunk_overlap=4)
    e = Engine.from_settings(s, embedder=HashEmbedder(32), reranker=LexicalReranker(), provider=FakeProvider([]))
    (s.raw_dir / "d1.md").write_text("Badge access requires a photo ID.")
    e.store.create_document("d1", "d1.md")
    assert await ingest_document({"engine": e}, "d1") == 1
    assert e.store.get_document("d1")["status"] == "ready"


def test_worker_settings_register_the_job():
    assert ingest_document in WorkerSettings.functions
    assert WorkerSettings.max_tries == 2
