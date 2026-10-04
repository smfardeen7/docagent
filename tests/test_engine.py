import json

from docagent.engine import Engine
from docagent.index import HashEmbedder
from docagent.llm import FakeProvider
from docagent.retrieve import LexicalReranker
from docagent.settings import Settings


def make(tmp_path, responses=None):
    s = Settings(data_dir=tmp_path, provider="fake", vector_backend="numpy", chunk_tokens=32, chunk_overlap=4)
    return Engine.from_settings(s, embedder=HashEmbedder(32), reranker=LexicalReranker(),
                                provider=FakeProvider(responses or []))


def add_doc(engine, doc_id, suffix, text):
    (engine.settings.raw_dir / f"{doc_id}{suffix}").write_text(text)
    engine.store.create_document(doc_id, f"{doc_id}{suffix}")
    return doc_id


def test_ingest_query_and_reload(tmp_path):
    writer = make(tmp_path)
    reader = make(tmp_path, ["Forty dollars [1]."])
    assert reader.ready() is False
    d = add_doc(writer, "handbook", ".md",
                "Meals are reimbursed up to forty dollars per day. Receipts are needed over 25 dollars.")
    n = writer.ingest(d)
    assert n >= 1 and writer.store.get_document(d)["status"] == "ready"
    assert (tmp_path / "index" / "version").read_text().strip() == "1"
    # a second process sees the new index without restarting
    assert reader.ready() is True
    ans, run_id, ms = reader.query("meal limit?")
    assert "Forty" in ans.text and ans.citations[0].doc_id == d
    assert reader.store.get_run(run_id)["mode"] == "rag" and ms >= 0


def test_second_ingest_bumps_version_and_extends_index(tmp_path):
    e = make(tmp_path)
    e.ingest(add_doc(e, "a", ".md", "Badge access requires a photo ID."))
    e.ingest(add_doc(e, "b", ".md", "Parental leave is twelve weeks at full pay."))
    assert (tmp_path / "index" / "version").read_text().strip() == "2"
    assert len(e.vector_index) == 2 and len(e.bm25_index) == 2
    assert e.retriever.search("parental leave", top_k=1)[0].doc_id == "b"


def test_ingest_failure_marks_document(tmp_path):
    e = make(tmp_path)
    (e.settings.raw_dir / "bad.docx").write_bytes(b"zz")
    e.store.create_document("bad", "bad.docx")
    assert e.ingest("bad") == 0
    assert e.store.get_document("bad")["status"] == "failed"
    assert e.ready() is False


def test_ingest_missing_raw_file_marks_failed(tmp_path):
    e = make(tmp_path)
    e.store.create_document("ghost", "ghost.md")
    assert e.ingest("ghost") == 0
    assert "missing" in e.store.get_document("ghost")["reason"]


def test_agent_run_is_stored_with_trace(tmp_path):
    e = make(tmp_path)
    e.ingest(add_doc(e, "h", ".md", "Parental leave is twelve weeks at full pay."))
    e._provider = FakeProvider([
        json.dumps({"thought": "s", "tool": "search_docs", "args": {"query": "leave"}}),
        json.dumps({"thought": "a", "tool": "final_answer", "args": {"answer": "Twelve weeks.", "citations": [1]}}),
        "Parental leave is twelve weeks [1].",  # grounded synthesis over the gathered chunk
    ])
    res, run_id, _ = e.agent("how long is leave?")
    run = e.store.get_run(run_id)
    assert run["mode"] == "agent" and len(run["steps"]) == 2 and run["fallback_used"] is False
    assert res.answer == "Parental leave is twelve weeks [1]." and run["citations"][0]["chunk_id"] == 1


def test_provider_error_marks_run_error_and_reraises(tmp_path):
    e = make(tmp_path)
    e.ingest(add_doc(e, "h", ".md", "Parental leave is twelve weeks."))
    e._provider = FakeProvider([])  # exhausted -> RuntimeError
    try:
        e.query("leave?")
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected provider error to propagate")
    runs = e.store._conn.execute("SELECT status FROM runs").fetchall()
    assert [r[0] for r in runs] == ["error"]
