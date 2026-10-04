"""Composes ingestion, indexing, retrieval, generation and persistence behind one object.

The API and the worker each hold their own Engine over the same data directory. The worker writes
index files atomically and bumps `index/version`; the API checks that file before every search and
reloads when it changes, so new documents are visible without a restart.
"""

import logging
import time
import uuid
from dataclasses import asdict

from docagent.agent import AgentResult, ToolRegistry, build_default_tools, run_agent
from docagent.index import BM25Index, VectorIndex
from docagent.index.embedder import Embedder, SentenceTransformerEmbedder
from docagent.ingest import Chunker, EmptyDocument, UnsupportedFileType, get_tokenizer, load_text
from docagent.llm import LLMProvider, make_provider
from docagent.rag import Answer, answer_question
from docagent.retrieve import CrossEncoderReranker, Reranker, Retriever
from docagent.settings import Settings
from docagent.store import Store

log = logging.getLogger(__name__)

BM25_FILE = "bm25.pkl"
VERSION_FILE = "version"


class Engine:
    def __init__(self, settings: Settings, store: Store, embedder: Embedder, reranker: Reranker,
                 provider: LLMProvider | None = None):
        self.settings = settings
        self.store = store
        self.embedder = embedder
        self.reranker = reranker
        self._provider = provider
        self.chunker = Chunker(get_tokenizer(settings.embedding_model), settings.chunk_tokens, settings.chunk_overlap)
        self._loaded_version = -1
        self.vector_index = VectorIndex(embedder.dim, settings.vector_backend)
        self.bm25_index = BM25Index.build([])
        self.reload_indexes_if_changed()

    @classmethod
    def from_settings(cls, settings: Settings, *, embedder: Embedder | None = None, reranker: Reranker | None = None,
                      provider: LLMProvider | None = None) -> "Engine":
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        settings.raw_dir.mkdir(parents=True, exist_ok=True)
        settings.index_dir.mkdir(parents=True, exist_ok=True)
        store = Store(settings.db_path)
        embedder = embedder or SentenceTransformerEmbedder(settings.embedding_model)
        reranker = reranker or CrossEncoderReranker(settings.reranker_model)
        return cls(settings, store, embedder, reranker, provider)

    # --- provider (lazy, so the worker never loads the generation model)
    @property
    def provider(self) -> LLMProvider:
        if self._provider is None:
            self._provider = make_provider(self.settings)
        return self._provider

    # --- index files
    @property
    def _version_path(self):
        return self.settings.index_dir / VERSION_FILE

    def _read_version(self) -> int:
        try:
            return int(self._version_path.read_text().strip())
        except (FileNotFoundError, ValueError):
            return 0

    def reload_indexes_if_changed(self) -> bool:
        v = self._read_version()
        if v == self._loaded_version:
            return False
        s = self.settings
        self.vector_index = VectorIndex.load(s.index_dir, self.embedder.dim, s.vector_backend)
        self.bm25_index = BM25Index.load(s.index_dir / BM25_FILE)
        self._loaded_version = v
        self.retriever = Retriever(self.embedder, self.vector_index, self.bm25_index, self.reranker, self.store,
                                   s.dense_k, s.bm25_k, s.rerank_k)
        self.tools: ToolRegistry = build_default_tools(self.retriever, self.store)
        return True

    def ready(self) -> bool:
        self.reload_indexes_if_changed()
        return len(self.vector_index) > 0

    # --- ingestion (worker side)
    def ingest(self, doc_id: str) -> int:
        doc = self.store.get_document(doc_id)
        if doc is None:
            raise KeyError(doc_id)
        self.store.set_document_status(doc_id, "processing")
        paths = list(self.settings.raw_dir.glob(f"{doc_id}.*"))
        try:
            if not paths:
                raise FileNotFoundError(f"raw file for {doc_id} missing")
            text = load_text(paths[0])
            chunks = self.chunker.split(text)
            if not chunks:
                raise EmptyDocument("no chunks produced")
        except (UnsupportedFileType, EmptyDocument, FileNotFoundError) as e:
            self.store.set_document_status(doc_id, "failed", reason=str(e), n_chunks=0)
            return 0

        ids = self.store.add_chunks(doc_id, chunks)
        self.reload_indexes_if_changed()
        self.vector_index.add(ids, self.embedder.encode([c.text for c in chunks]))
        self.store.set_document_status(doc_id, "ready", n_chunks=len(ids))
        self.bm25_index = BM25Index.build(self.store.all_chunks())
        self.vector_index.save(self.settings.index_dir)
        self.bm25_index.save(self.settings.index_dir / BM25_FILE)
        new_version = self._read_version() + 1
        tmp = self._version_path.with_suffix(".tmp")
        tmp.write_text(str(new_version))
        tmp.replace(self._version_path)
        self._loaded_version = -1
        self.reload_indexes_if_changed()
        log.info("ingested %s: %d chunks, index version %d", doc_id, len(ids), new_version)
        return len(ids)

    # --- serving (API side)
    def query(self, question: str, top_k: int | None = None) -> tuple[Answer, str, float]:
        self.reload_indexes_if_changed()
        run_id = uuid.uuid4().hex
        self.store.create_run(run_id, "rag", question)
        t0 = time.perf_counter()
        try:
            ans = answer_question(question, self.retriever, self.provider, top_k or self.settings.top_k,
                                  self.settings.max_new_tokens)
        except Exception:
            self.store.finish_run(run_id, None, [], "error", (time.perf_counter() - t0) * 1000)
            raise
        ms = (time.perf_counter() - t0) * 1000
        self.store.finish_run(run_id, ans.text, [asdict(c) for c in ans.citations], "ok", ms)
        return ans, run_id, ms

    def agent(self, question: str, max_steps: int | None = None) -> tuple[AgentResult, str, float]:
        self.reload_indexes_if_changed()
        run_id = uuid.uuid4().hex
        self.store.create_run(run_id, "agent", question)
        t0 = time.perf_counter()
        try:
            res = run_agent(question, self.tools, self.provider, self.retriever, self.store,
                            max_steps or self.settings.max_steps, self.settings.max_new_tokens,
                            on_step=lambda s: self.store.add_trace_step(run_id, asdict(s)))
        except Exception:
            self.store.finish_run(run_id, None, [], "error", (time.perf_counter() - t0) * 1000)
            raise
        ms = (time.perf_counter() - t0) * 1000
        self.store.finish_run(run_id, res.answer, [asdict(c) for c in res.citations], "ok", ms, res.fallback_used)
        return res, run_id, ms
