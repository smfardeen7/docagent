import json

import pytest
from fastapi.testclient import TestClient

from docagent.api import create_app
from docagent.engine import Engine
from docagent.index import HashEmbedder
from docagent.llm import FakeProvider
from docagent.retrieve import LexicalReranker
from docagent.settings import Settings


def scripted(msgs):
    if "Sources:" in msgs[-1].content:  # plain RAG prompt
        return "Forty dollars [1]."
    return json.dumps({"thought": "a", "tool": "final_answer", "args": {"answer": "Forty.", "citations": [1]}})


@pytest.fixture
def client(tmp_path):
    s = Settings(data_dir=tmp_path, provider="fake", vector_backend="numpy", chunk_tokens=32, chunk_overlap=4)
    engine = Engine.from_settings(s, embedder=HashEmbedder(32), reranker=LexicalReranker(), provider=FakeProvider(scripted))

    async def inline_enqueue(doc_id: str):
        engine.ingest(doc_id)

    return TestClient(create_app(engine, inline_enqueue))


def test_query_before_any_document_is_409(client):
    r = client.post("/query", json={"question": "meals?"})
    assert r.status_code == 409 and r.json()["detail"] == "no documents indexed"


def test_upload_query_agent_run_roundtrip(client):
    r = client.post("/documents", files={"file": ("handbook.md", b"Meals are reimbursed up to forty dollars per day.", "text/markdown")})
    assert r.status_code == 202
    doc_id = r.json()["doc_id"]
    assert client.get(f"/documents/{doc_id}").json()["status"] == "ready"
    assert client.get("/documents").json()[0]["filename"] == "handbook.md"
    q = client.post("/query", json={"question": "meal limit?", "top_k": 1}).json()
    assert "Forty" in q["answer"] and q["citations"][0]["chunk_id"] >= 1 and q["run_id"]
    a = client.post("/agent/run", json={"question": "meal limit?"}).json()
    # the agent's final_answer cites chunk 1; the answer is then synthesized over that evidence
    assert a["answer"] == "Forty dollars [1]." and a["fallback_used"] is False and a["steps"][0]["tool"] == "final_answer"
    assert a["citations"][0]["chunk_id"] == 1
    run = client.get(f"/runs/{a['run_id']}").json()
    assert run["mode"] == "agent" and len(run["steps"]) == 1
    assert client.get("/runs/nope").status_code == 404
    assert client.get("/documents/nope").status_code == 404


def test_unsupported_upload_is_415(client):
    r = client.post("/documents", files={"file": ("x.docx", b"zz", "application/octet-stream")})
    assert r.status_code == 415


def test_oversized_upload_is_413(client):
    client.app.state.engine.settings.max_upload_bytes = 10
    r = client.post("/documents", files={"file": ("big.md", b"x" * 11, "text/markdown")})
    assert r.status_code == 413


def test_validation_errors_are_422(client):
    assert client.post("/query", json={"question": ""}).status_code == 422
    assert client.post("/agent/run", json={"question": "q", "max_steps": 99}).status_code == 422


def test_provider_failure_is_503(client, monkeypatch):
    client.post("/documents", files={"file": ("h.md", b"Meals are forty dollars.", "text/markdown")})
    client.app.state.engine._provider = FakeProvider([])  # exhausted -> RuntimeError
    r = client.post("/query", json={"question": "meals?"})
    assert r.status_code == 503 and "generation failed" in r.json()["detail"]


def test_health_and_metrics(client):
    h = client.get("/healthz").json()
    assert h["status"] == "ok" and h["ready"] is False and h["provider"] == "fake"
    body = client.get("/metrics").text
    assert "docagent_http_requests_total" in body
