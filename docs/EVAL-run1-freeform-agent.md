# Evaluation

Generated 2026-10-04 01:36 UTC by `python -m docagent.eval` on arm64 Darwin (mps).
Provider: `hf:Qwen/Qwen2.5-1.5B-Instruct`. Embeddings: `BAAI/bge-small-en-v1.5`. Reranker: `cross-encoder/ms-marco-MiniLM-L-6-v2`. Vector backend: `numpy`.
Corpus: 8 synthetic handbook documents in `eval/corpus/` (32 chunks), 40 hand-written questions in `eval/questions.jsonl`.
Everything here is reproducible by cloning the repo and running the command above. Latencies are single-process on the machine named, not a production SLA.

## Retrieval (hybrid dense + BM25, cross-encoder rerank)

| recall@1 | recall@3 | recall@5 | MRR | p50 | p95 |
|---|---|---|---|---|---|
| 87.5% | 100.0% | 100.0% | 0.925 | 60 ms | 98 ms |

## Answers

| Mode | keyword hit rate | citation precision | p50 | p95 |
|---|---|---|---|---|
| RAG (single pass) | 92.5% | 100.0% | 2.6 s | 5.7 s |
| Agent (ReAct) | 47.5% | 44.5% | 11.2 s | 28.0 s |

Agent tool-call validity: 97.5%. Mean steps: 3.23. Fallback to plain RAG: 15.0% of runs.

## By question kind

| kind | n | recall@5 | RAG hit | Agent hit |
|---|---|---|---|---|
| calc | 4 | 100.0% | 50.0% | 25.0% |
| lookup | 30 | 100.0% | 96.7% | 46.7% |
| multi | 6 | 100.0% | 100.0% | 66.7% |

## How to read this

- *keyword hit rate*: all expected keywords appear in the answer. A strict proxy for correctness; it under-counts paraphrases.
- *citation precision*: fraction of cited chunks that contain the gold passage.
- *tool-call validity*: valid JSON tool calls / all model turns in agent mode.
- *fallback*: the agent gave up (two unparseable turns, step budget, or empty answer) and the question was answered by single-pass RAG instead. Fallback runs still count toward the agent's hit rate.
- The generation model is a 1.5B-parameter local model; these numbers describe this configuration only.
