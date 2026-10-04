# DocAgent — design spec

Date: 2026-10-03. Status: approved in conversation, implementation pending.

## Purpose

A self-hosted agentic retrieval-augmented-generation (RAG) assistant over a user's own documents. It exists as a portfolio project that demonstrates, with running code and measured results, the skills that 2027 new-grad AI-engineer postings list and the author's resume currently lacks: Hugging Face Transformers, embeddings and vector search, RAG, agentic tool use, Kubernetes, and AWS deployment readiness.

Success means: every resume bullet written about this project is backed by code in this repo, a test, or a number in `docs/EVAL.md`. Nothing is claimed that the repo does not show.

## Non-goals

- Multi-tenant auth, billing, or user accounts.
- GPU or distributed training/inference.
- Production SLAs. The local Hugging Face model is small; answer quality is measured and reported, not promised.
- Live cloud deployment in this phase. Terraform is written and validated; it is applied only when the owner adds credentials.

## Architecture

```
browser ── React/TS UI ──► FastAPI api ──► SQLite (docs, chunks, runs, traces)
                             │  ▲             FAISS index + BM25 (on disk)
                             │  └── search/answer/agent (in-process)
                             └── enqueue ingest job ──► Redis ──► arq worker ──► embed + index
```

Components, each a Python package under `docagent/`:

| Module | Responsibility | Depends on |
|---|---|---|
| `ingest` | Load PDF/Markdown/text, split into token-aware chunks with overlap, return `Chunk` records | `transformers` tokenizer, `pypdf` |
| `index` | Embed chunks (`BAAI/bge-small-en-v1.5` via sentence-transformers), persist FAISS index + BM25 corpus, load/save atomically | `sentence_transformers`, `faiss`, `rank_bm25` |
| `retrieve` | Hybrid search (dense + BM25, reciprocal rank fusion) then cross-encoder rerank (`cross-encoder/ms-marco-MiniLM-L-6-v2`); returns ranked `Hit`s with scores | `index` |
| `llm` | `LLMProvider` protocol with `generate(messages, max_tokens) -> str`. Implementations: `HFLocalProvider` (Qwen2.5-1.5B-Instruct, MPS or CPU), `AnthropicProvider` (optional, env `ANTHROPIC_API_KEY`), `FakeProvider` (tests) | `transformers` |
| `rag` | Plain RAG: retrieve → build cited prompt → generate → parse `[n]` citations into structured `Answer` | `retrieve`, `llm` |
| `agent` | ReAct loop: tool registry, strict JSON tool-call parser, step limit, per-step trace; falls back to `rag.answer` when the model fails to emit a valid call twice in a row | `rag`, `llm` |
| `store` | SQLite schema and CRUD for documents, chunks, runs, traces | stdlib `sqlite3` |
| `api` | FastAPI app, Prometheus metrics, job enqueue | all above, `arq` |
| `worker` | arq worker: `ingest_document(doc_id)` → ingest → index → mark ready | `ingest`, `index`, `store` |
| `eval` | Runs the labeled question set, computes metrics, writes `docs/EVAL.md` and `eval/results.json` | `retrieve`, `rag`, `agent` |

Settings come from `pydantic-settings` (`DOCAGENT_*` env vars): data dir, model names, provider choice, Redis URL, top-k values, agent step limit.

## Data flow

1. `POST /documents` saves the upload under `data/raw/<doc_id>`, inserts a `documents` row with status `queued`, enqueues `ingest_document`. Returns `202 {doc_id}`.
2. Worker loads the file, chunks it (target 256 tokens, 32 overlap, measured with the embedding model's tokenizer), embeds in batches, appends to FAISS and BM25, writes chunk rows, sets status `ready`. Index files are written to a temp path and renamed, so a crash never leaves a half-written index.
3. `POST /query {question, top_k}` runs hybrid retrieval, reranks to `top_k` (default 5), generates a cited answer, stores a `runs` row with mode `rag`, returns `{answer, citations[], run_id, latency_ms}`.
4. `POST /agent/run {question, max_steps}` runs the agent loop. Each step records `{thought, tool, args, observation}` in `traces`. Returns `{answer, citations[], steps[], run_id, fallback_used}`.
5. `GET /runs/{id}` returns the stored run and trace. `GET /documents` lists documents with status. `GET /healthz`, `GET /metrics` (Prometheus: request count/latency per route, retrieval latency, generation tokens, agent steps, fallback counter).

## Agent design

Tools (each a function with a JSON-schema signature, registered in `agent/tools.py`):

- `search_docs(query, k)` → list of `{chunk_id, doc, score, text}`
- `read_chunk(chunk_id)` → full chunk text with neighbors (±1 chunk)
- `compare(chunk_ids[])` → the chunks concatenated with labels, for side-by-side reasoning
- `calculate(expression)` → safe arithmetic via `ast` (no `eval`)
- `final_answer(answer, citations[])` → terminates the loop

Prompt format: system prompt lists tools with schemas and requires each turn to be exactly one JSON object `{"thought": str, "tool": str, "args": {}}`. The parser extracts the first balanced JSON object; anything else is a parse failure. Two consecutive failures, or reaching `max_steps` (default 6), triggers fallback to plain RAG, and the run is flagged `fallback_used=true`. This keeps the small local model honest: the eval reports the fallback rate rather than hiding it.

**Revision (2026-10-04, after the first evaluation run).** `final_answer` no longer supplies the answer text. The loop records the chunk ids seen in `search_docs`/`read_chunk`/`compare` observations and the results of `calculate`; on `final_answer` it generates the answer with the plain-RAG cited-sources prompt over those chunks (cited ids first, up to 8) with computed values appended to the question, and parses citations from that output. `final_answer` with no gathered evidence, or an empty synthesis, also falls back to plain RAG. Reason: run 1 measured retrieval recall@5 100%, RAG keyword hit 92.5%, agent free-form answers 47.5% with 97.5% valid tool calls — the loss was in answering, not in retrieval or tool use. `search_docs` previews grew from 300 to 700 characters and default `k` from 5 to 3.

## Evaluation

- Corpus: `eval/corpus/` — synthetic employee-handbook documents for a fictional company (CC0, written for this project), so the eval is reproducible by anyone who clones and no real policy is implied.
- Questions: `eval/questions.jsonl` — about 40 items, each `{question, gold_doc, gold_chunk_substring, answer_keywords[]}` written by hand.
- Metrics, computed by `python -m docagent.eval`:
  - Retrieval: recall@1/3/5 (gold substring appears in a returned chunk), MRR.
  - Answer: keyword hit rate (all `answer_keywords` present), citation precision (cited chunks that contain the gold substring / cited chunks).
  - Agent: tool-call validity rate, mean steps, fallback rate, same answer metrics.
  - Latency: p50/p95 for retrieval, RAG, and agent on the author's M4 (CPU/MPS), clearly labeled as such.
- Output: `eval/results.json` plus a rendered `docs/EVAL.md`. Resume bullets quote only from this file.

## Frontend

`frontend/` — Vite + React + TypeScript. One page: document list with upload and status, a chat panel that calls `/query` or `/agent/run` (toggle), renders the answer with inline `[n]` citations that expand to the chunk, and a collapsible agent trace. No state library; `fetch` + React state. Built to static files served by nginx in the container.

## Infrastructure

- `Dockerfile` (multi-stage: builder with uv, slim runtime; same image runs `api` or `worker` by command).
- `frontend/Dockerfile` (node build → nginx).
- `compose.yaml`: `api`, `worker`, `redis`, `ui`; models cached in a named volume; `--wait` healthchecks.
- `deploy/k8s/` (kustomize): Namespace, ConfigMap, Redis Deployment+Service, api Deployment+Service (readiness on `/healthz`), worker Deployment, HPA on api CPU, PVC for data. `scripts/kind-up.sh` creates a kind cluster, loads the local images, applies manifests, waits for rollout, and runs a smoke query. CI runs this script.
- `deploy/terraform/aws/`: ECS Fargate service for api + worker, ElastiCache Redis, EFS for data, ALB, ECR repos. `terraform init -backend=false && terraform validate` runs in CI. Not applied in this phase; README states this plainly.
- `.github/workflows/ci.yml`: backend tests, frontend build, image builds, kind smoke test, terraform validate.

## Testing

- Unit: chunker (token budgets, overlap, boundaries), BM25/RRF fusion math, citation parser, tool-call parser (valid, malformed, nested JSON, prose around JSON), `calculate` safety (rejects names/calls).
- Integration (fast, `FakeProvider`, tiny embedding fixture or real `bge-small` on 3 short docs): ingest → index → retrieve returns the planted chunk; RAG answer carries citations; agent completes a scripted tool sequence; fallback triggers after two bad calls.
- API: FastAPI `TestClient` with an in-memory arq stub; upload → status → query round trip.
- Target: tests run in under 2 minutes on CI without downloading the generation model (tests never load Qwen).

## Error handling

- Unsupported file type → `415`. Empty extraction → document status `failed` with reason.
- Index missing (no documents yet) → `/query` returns `409 {detail: "no documents indexed"}`.
- Provider errors (OOM, API failure) → run stored with status `error`, `503` to the client, counter incremented.
- Worker job failure → retried once by arq, then status `failed`.

## Resume bullets this spec supports (final wording after eval)

- Built an agentic RAG assistant on Hugging Face Transformers: `bge-small` embeddings with FAISS + BM25 hybrid retrieval, cross-encoder reranking, and a local Qwen2.5 model behind a pluggable provider interface.
- Implemented a ReAct agent with a typed tool registry, strict tool-call parsing, and traced runs; measured retrieval recall@5 of __, MRR __, and agent tool-call validity of __ on a 40-question labeled set.
- Shipped FastAPI + Redis/arq ingestion workers, Prometheus metrics, a React/TypeScript UI, Kubernetes manifests verified on kind in CI, and validated Terraform for AWS ECS Fargate.
