"""Regression tests for the findings of the whole-branch review (see .superpowers ledger, Final: lines)."""

import threading
import time

import numpy as np

from docagent.agent.calc import safe_calculate
from docagent.engine import Engine
from docagent.index import HashEmbedder
from docagent.ingest.chunker import Chunk
from docagent.llm import FakeProvider
from docagent.retrieve import LexicalReranker
from docagent.settings import Settings
from docagent.store import Store
from docagent.worker.main import WorkerSettings


def make(tmp_path, embedder=None):
    s = Settings(data_dir=tmp_path, provider="fake", vector_backend="numpy", chunk_tokens=32, chunk_overlap=4)
    return Engine.from_settings(s, embedder=embedder or HashEmbedder(32), reranker=LexicalReranker(),
                                provider=FakeProvider([]))


def add_doc(engine, doc_id, text):
    (engine.settings.raw_dir / f"{doc_id}.md").write_text(text)
    engine.store.create_document(doc_id, f"{doc_id}.md")
    return doc_id


class SlowEmbedder(HashEmbedder):
    """Widens the encode window so an unlocked concurrent ingest would interleave."""

    def encode(self, texts):
        time.sleep(0.3)
        return super().encode(texts)


# --- Critical 1: concurrent ingests must not lose vectors
def test_concurrent_ingests_keep_every_vector(tmp_path):
    e = make(tmp_path, embedder=SlowEmbedder(32))
    ids = [add_doc(e, f"d{i}", f"Document {i} about topic {i} with some words.") for i in range(3)]
    threads = [threading.Thread(target=e.ingest, args=(d,)) for d in ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(e.vector_index) == e.store.count_ready_chunks() == 3
    assert e._read_version() == 3


def test_worker_runs_one_job_at_a_time():
    assert WorkerSettings.max_jobs == 1


# --- Important 2: any ingest failure marks the document failed; re-runs do not duplicate chunks
class ExplodingEmbedder(HashEmbedder):
    def __init__(self, dim=32):
        super().__init__(dim)
        self.calls = 0

    def encode(self, texts):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("simulated embedder crash")
        return super().encode(texts)


def test_unexpected_error_marks_failed_and_rerun_has_no_duplicate_chunks(tmp_path):
    e = make(tmp_path, embedder=ExplodingEmbedder(32))
    d = add_doc(e, "h", "Meals are forty dollars per day while travelling.")
    assert e.ingest(d) == 0
    doc = e.store.get_document(d)
    assert doc["status"] == "failed" and "simulated embedder crash" in doc["reason"]
    assert e.store.count_ready_chunks() == 0
    n = e.ingest(d)  # second attempt succeeds
    assert n >= 1 and e.store.get_document(d)["status"] == "ready"
    rows = e.store._conn.execute("SELECT COUNT(*) FROM chunks WHERE doc_id=?", (d,)).fetchone()[0]
    assert rows == n, "chunks from the failed attempt must not remain"
    assert len(e.vector_index) == n


def test_not_really_a_pdf_marks_failed(tmp_path):
    e = make(tmp_path)
    (e.settings.raw_dir / "bad.pdf").write_bytes(b"this is not a pdf")
    e.store.create_document("bad", "bad.pdf")
    assert e.ingest("bad") == 0
    assert e.store.get_document("bad")["status"] == "failed"


def test_ready_only_after_index_is_saved(tmp_path):
    e = make(tmp_path)
    d = add_doc(e, "h", "Badge access requires a photo ID.")
    e.ingest(d)
    assert e.store.get_document(d)["status"] == "ready"
    assert (tmp_path / "index" / "vectors.npz").exists() and (tmp_path / "index" / "bm25.pkl").exists()
    # a brand-new engine loading from disk sees the document in both indexes
    fresh = make(tmp_path)
    assert len(fresh.vector_index) == 1 and len(fresh.bm25_index) == 1


def test_store_all_chunks_can_include_a_processing_document(tmp_path):
    s = Store(tmp_path / "t.db")
    s.create_document("r", "r.md")
    s.add_chunks("r", [Chunk(0, "ready text", 2)])
    s.set_document_status("r", "ready", n_chunks=1)
    s.create_document("p", "p.md")
    s.add_chunks("p", [Chunk(0, "processing text", 2)])
    s.set_document_status("p", "processing")
    assert [t for _, t in s.all_chunks()] == ["ready text"]
    assert [t for _, t in s.all_chunks(including="p")] == ["ready text", "processing text"]
    assert s.delete_chunks("p") == 1
    assert s.all_chunks(including="p") == [(1, "ready text")]


# --- Important 3: calculate must bound the size of the result, not just one exponent
def test_nested_powers_are_rejected_fast():
    t0 = time.perf_counter()
    out = safe_calculate("(((10**64)**64)**64)**64")
    assert out.startswith("error:") and (time.perf_counter() - t0) < 1.0


def test_large_but_bounded_power_still_works():
    assert safe_calculate("2**100") == str(2**100)
    assert safe_calculate("2**4000").startswith("error:")  # result too large to be useful in an answer


def test_huge_result_string_is_an_error_not_an_exception():
    out = safe_calculate("9**1300")
    assert isinstance(out, str) and (out.startswith("error:") or len(out) > 100)


# --- Minor 6 and 10 (folded in): cited ids must have been observed; fallback honours top_k
def test_unobserved_cited_ids_are_ignored_and_newest_evidence_is_kept(tmp_path):
    import json

    from docagent.agent import build_default_tools, run_agent
    from docagent.retrieve import Hit

    store = Store(tmp_path / "t.db")
    store.create_document("d", "d.md")
    store.add_chunks("d", [Chunk(i, f"chunk {i} text", 3) for i in range(12)])
    store.set_document_status("d", "ready", n_chunks=12)

    class R:
        def search(self, q, top_k=5):
            return [Hit(i, "d", i - 1, f"chunk {i - 1} text", 1.0) for i in range(1, 11)][:top_k]

    reg = build_default_tools(R(), store)

    def call(tool, **args):
        return json.dumps({"thought": "t", "tool": tool, "args": args})

    p = FakeProvider([
        call("search_docs", query="a", k=10),           # observes chunks 1..10
        call("read_chunk", chunk_id=12),                # observes 11, 12 (neighbours)
        call("final_answer", answer="x", citations=[999, 12]),  # 999 was never observed
        "answer [1] [2]",
    ])
    r = run_agent("q", reg, p, R(), store, max_steps=6)
    prompt = p.calls[-1][-1].content
    assert "[1] chunk 11 text" in prompt           # cited and observed → first
    assert "chunk 999" not in prompt               # never observed → ignored
    assert "[8] chunk 10 text" in prompt           # newest observations kept when capped
    assert r.citations[0].chunk_id == 12
