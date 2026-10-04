from docagent.ingest.chunker import Chunk
from docagent.store import Store


def make(tmp_path):
    return Store(tmp_path / "t.db")


def test_document_lifecycle(tmp_path):
    s = make(tmp_path)
    s.create_document("d1", "a.md")
    assert s.get_document("d1")["status"] == "queued"
    ids = s.add_chunks("d1", [Chunk(0, "alpha", 1), Chunk(1, "beta", 1)])
    assert ids == [1, 2]
    s.set_document_status("d1", "ready", n_chunks=2)
    d = s.get_document("d1")
    assert d["status"] == "ready" and d["n_chunks"] == 2
    assert s.count_ready_chunks() == 2
    assert [c["text"] for c in s.get_chunks([2, 1])] == ["beta", "alpha"]
    assert s.all_chunks() == [(1, "alpha"), (2, "beta")]
    assert [c["id"] for c in s.neighbors(1)] == [1, 2]


def test_failed_doc_chunks_not_counted(tmp_path):
    s = make(tmp_path)
    s.create_document("d1", "a.pdf")
    s.set_document_status("d1", "failed", reason="no text extracted")
    assert s.count_ready_chunks() == 0
    assert s.get_document("d1")["reason"] == "no text extracted"


def test_run_and_trace(tmp_path):
    s = make(tmp_path)
    s.create_run("r1", "agent", "q?")
    s.add_trace_step("r1", {"n": 1, "thought": "t", "tool": "search_docs", "args": {"query": "q"}, "observation": "o"})
    s.finish_run("r1", "ans", [{"n": 1, "chunk_id": 3}], "ok", 12.5, fallback_used=True)
    r = s.get_run("r1")
    assert r["answer"] == "ans" and r["fallback_used"] is True
    assert r["citations"][0]["chunk_id"] == 3
    assert r["steps"][0]["tool"] == "search_docs"
