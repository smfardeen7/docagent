# Architecture

```
browser ── React/TS UI (nginx) ──► FastAPI api ──► SQLite  (documents, chunks, runs, traces)
                                     │  ▲          vector index + BM25 pickle  (on disk, versioned)
                                     │  └── retrieve → rerank → generate / agent   (in-process)
                                     └── enqueue ingest job ──► Redis ──► arq worker ──► chunk → embed → index
```

## Request paths

**Upload.** `POST /documents` stores the raw file under `data/raw/<doc_id>.<ext>`, inserts a `documents` row
with status `queued`, and enqueues `ingest_document(doc_id)` on Redis. The API returns `202` immediately.

**Ingest (worker).** `Engine.ingest` loads the file (PDF via pypdf, Markdown/text as-is), splits it into
256-token windows with 32-token overlap using the embedding model's tokenizer, writes chunk rows, embeds the
chunks with `BAAI/bge-small-en-v1.5`, appends to the vector index, rebuilds BM25 over all ready chunks
(BM25's IDF needs the whole corpus), writes both index files to a temp path and renames them, then bumps
`index/version`. A crash mid-ingest never leaves a half-written index on disk.

**Index reload (API).** Before every search the API compares `index/version` with the version it loaded.
When the worker has bumped it, the API reloads both indexes. The API and worker share the data directory
(a Compose volume, a Kubernetes PVC, or EFS on AWS), so new documents become searchable without a restart.

**Query.** `POST /query` runs hybrid retrieval — dense top-20 by inner product and BM25 top-20, merged with
reciprocal rank fusion — then reranks the top 10 with the cross-encoder `ms-marco-MiniLM-L-6-v2` and keeps
`top_k`. The prompt numbers the sources `[1]..[k]`; the model must cite with `[n]`; the citation parser maps
markers back to chunk ids and drops duplicates and out-of-range numbers. The run and its citations are stored.

**Agent.** `POST /agent/run` runs a ReAct loop. Each turn the model must reply with one JSON object
`{"thought", "tool", "args"}`. The parser extracts the first balanced JSON object (code fences and prose
around it are tolerated) and validates the shape. Tools (`search_docs`, `read_chunk`, `compare`,
`calculate`) never raise into the loop; failures come back as `error: ...` observations. Chunk ids that appear
in `search_docs`/`read_chunk`/`compare` observations are collected as *evidence*; `calculate` results are kept
as *computed values*. When the model calls `final_answer`, the answer is not taken from its free text: the
grounded RAG prompt is run over the evidence chunks (the ones the model cited first, then the rest it saw) with
the computed values appended to the question, and the citations are parsed from that synthesis. Two consecutive
unparseable turns, an exhausted step budget, a `final_answer` with no evidence, or an empty synthesis trigger a
fallback to single-pass RAG, and the run is flagged `fallback_used`. Every step is written to `traces` as it
happens, so a run that crashes mid-way still leaves its partial trace.

Why the split between gathering and answering: the first evaluation run (`docs/EVAL-run1-freeform-agent.md`)
measured retrieval recall@5 at 100% and single-pass RAG at 92.5% keyword hit rate, but the agent's free-form final
answers at 47.5% — the 1.5B model saw short previews, rarely read chunks, and then wrote confident wrong
sentences. Letting the agent decide *what* to read and the grounded prompt decide *what to say* is the fix the
numbers pointed at; `docs/EVAL.md` has the re-measured result.

## Components

| Package | Responsibility |
|---|---|
| `docagent.ingest` | loaders (`load_text`), token-aware `Chunker` |
| `docagent.index` | `Embedder` (sentence-transformers / hashing fake), `VectorIndex` (numpy or faiss backend), `BM25Index` |
| `docagent.retrieve` | reciprocal rank fusion, `Reranker` (cross-encoder / lexical fake), `Retriever` |
| `docagent.llm` | `LLMProvider` protocol; `HFLocalProvider` (transformers, MPS/CUDA/CPU), `AnthropicProvider`, `FakeProvider` |
| `docagent.rag` | prompt construction, citation parsing, `answer_question` |
| `docagent.agent` | safe calculator, tool registry, tool-call parser, ReAct loop |
| `docagent.store` | SQLite (WAL) persistence |
| `docagent.engine` | composes everything; owns index files and the version-reload protocol |
| `docagent.api` | FastAPI app, Prometheus metrics |
| `docagent.worker` | arq job and worker settings |
| `docagent.eval` | reproducible evaluation and report rendering |

## Vector backend

`VectorIndex` has two exact inner-product backends with identical rankings: `faiss` (default on Linux —
containers, Kubernetes, CI) and `numpy` (default on macOS). On macOS, `faiss-cpu` and `torch` each bundle
their own OpenMP runtime and the process aborts when both load, so the pure-NumPy backend is used there.
`DOCAGENT_VECTOR_BACKEND` overrides the default.

## Why these choices

- **Hybrid retrieval.** Handbook questions often hinge on exact tokens (a dollar figure, a product name)
  where BM25 is strong, and on paraphrase where dense retrieval is strong. RRF needs no score calibration.
- **Cross-encoder rerank.** Cheap at `rerank_k=10` and markedly better at ordering than either retriever.
- **Local model by default.** The project runs with no API key and no cost; the provider interface keeps a
  hosted model one env var away.
- **Strict tool calls + measured fallback.** A 1.5B model will sometimes break the JSON contract. Rather than
  hide that, the loop falls back deterministically and the evaluation reports the rate.
- **SQLite + files, not a vector database.** The corpus sizes this serves (thousands of chunks) do not need
  one, and the whole system stays inspectable with `sqlite3` and `ls`.

## Limits

- No authentication or multi-tenancy.
- Index reload is per process; with several API replicas each reloads independently (fine) but the worker
  must be a single replica, because ingestion appends to one index.
- Answer quality is bounded by the 1.5B local model; see `docs/EVAL.md` for measured numbers.
