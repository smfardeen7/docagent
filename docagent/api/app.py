import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from docagent.engine import Engine
from docagent.ingest.loaders import TEXT_SUFFIXES

from . import metrics as M
from .schemas import AgentRequest, AgentResponse, QueryRequest, QueryResponse

ALLOWED = TEXT_SUFFIXES | {".pdf"}


def create_app(engine: Engine, enqueue: Callable[[str], Awaitable[None]]) -> FastAPI:
    """`enqueue(doc_id)` hands ingestion to the worker; tests pass an inline coroutine instead of Redis."""
    app = FastAPI(title="DocAgent", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.middleware("http")(M.metrics_middleware)
    app.state.engine = engine

    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "ready": engine.ready(), "provider": engine.settings.provider}

    @app.get("/metrics")
    def metrics():
        return M.metrics_endpoint()

    @app.post("/documents", status_code=202)
    async def upload(file: UploadFile = File(...)):
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in ALLOWED:
            raise HTTPException(415, f"unsupported file type {suffix or '(none)'}; allowed: {sorted(ALLOWED)}")
        data = await file.read()
        if len(data) > engine.settings.max_upload_bytes:
            raise HTTPException(413, "file too large")
        doc_id = uuid.uuid4().hex
        (engine.settings.raw_dir / f"{doc_id}{suffix}").write_bytes(data)
        engine.store.create_document(doc_id, file.filename or f"{doc_id}{suffix}")
        await enqueue(doc_id)
        return {"doc_id": doc_id, "status": engine.store.get_document(doc_id)["status"]}

    @app.get("/documents")
    def list_documents():
        return engine.store.list_documents()

    @app.get("/documents/{doc_id}")
    def get_document(doc_id: str):
        doc = engine.store.get_document(doc_id)
        if not doc:
            raise HTTPException(404, "document not found")
        return doc

    def _require_ready() -> None:
        if not engine.ready():
            raise HTTPException(409, "no documents indexed")

    @app.post("/query", response_model=QueryResponse)
    def query(req: QueryRequest):
        _require_ready()
        try:
            with M.RUN_LATENCY.labels("rag").time():
                ans, run_id, ms = engine.query(req.question, req.top_k)
        except Exception as e:
            M.RUN_ERRORS.labels("rag").inc()
            raise HTTPException(503, f"generation failed: {type(e).__name__}") from e
        return QueryResponse(answer=ans.text, citations=[asdict(c) for c in ans.citations], run_id=run_id, latency_ms=ms)

    @app.post("/agent/run", response_model=AgentResponse)
    def agent_run(req: AgentRequest):
        _require_ready()
        try:
            with M.RUN_LATENCY.labels("agent").time():
                res, run_id, ms = engine.agent(req.question, req.max_steps)
        except Exception as e:
            M.RUN_ERRORS.labels("agent").inc()
            raise HTTPException(503, f"agent failed: {type(e).__name__}") from e
        M.AGENT_STEPS.observe(len(res.steps))
        if res.fallback_used:
            M.FALLBACKS.inc()
        return AgentResponse(
            answer=res.answer,
            citations=[asdict(c) for c in res.citations],
            run_id=run_id,
            latency_ms=ms,
            steps=[asdict(s) for s in res.steps],
            fallback_used=res.fallback_used,
            parse_failures=res.parse_failures,
        )

    @app.get("/runs/{run_id}")
    def get_run(run_id: str):
        run = engine.store.get_run(run_id)
        if not run:
            raise HTTPException(404, "run not found")
        return run

    return app
