"""Reproducible evaluation: `python -m docagent.eval [--provider hf|anthropic|fake] [--limit N]`.

Indexes eval/corpus/ from scratch, runs every question through retrieval, single-pass RAG and the agent,
and writes eval/results.json plus a rendered docs/EVAL.md. Resume bullets quote only from that output.
"""

import argparse
import json
import platform
import shutil
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from docagent.engine import Engine
from docagent.settings import Settings

from .metrics import citation_precision, keyword_hit, percentile, recall_at_k, reciprocal_rank

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "eval" / "corpus"
QUESTIONS = ROOT / "eval" / "questions.jsonl"


def load_questions(limit: int | None) -> list[dict]:
    qs = [json.loads(line) for line in QUESTIONS.read_text().splitlines() if line.strip()]
    return qs[:limit] if limit else qs


def build_engine(data_dir: Path, provider: str) -> Engine:
    if data_dir.exists():
        shutil.rmtree(data_dir)
    s = Settings(data_dir=data_dir, provider=provider)
    if provider == "fake":
        from docagent.index import HashEmbedder
        from docagent.llm import FakeProvider
        from docagent.retrieve import LexicalReranker

        e = Engine.from_settings(s, embedder=HashEmbedder(64), reranker=LexicalReranker(),
                                 provider=FakeProvider(lambda m: "No answer available."))
    else:
        e = Engine.from_settings(s)
    for path in sorted(CORPUS.glob("*.md")):
        if path.name == "README.md":
            continue
        doc_id = path.stem
        shutil.copy(path, s.raw_dir / f"{doc_id}.md")
        e.store.create_document(doc_id, path.name)
        e.ingest(doc_id)
    return e


def evaluate(engine: Engine, questions: list[dict], top_k: int, max_steps: int, log=print) -> dict:
    retr_lat: list[float] = []
    rag_lat: list[float] = []
    agent_lat: list[float] = []
    r1 = r3 = r5 = mrr = 0.0
    rag_kw: list[bool] = []
    rag_cp: list[float] = []
    ag_kw: list[bool] = []
    ag_cp: list[float] = []
    ag_steps: list[int] = []
    ag_valid: list[float] = []
    ag_fb = 0
    per_q: list[dict] = []

    for i, q in enumerate(questions, start=1):
        gold = q["gold_substring"]
        t0 = time.perf_counter()
        hits = engine.retriever.search(q["question"], top_k=5)
        retr_lat.append((time.perf_counter() - t0) * 1000)
        texts = [h.text for h in hits]
        r1 += recall_at_k(texts, gold, 1)
        r3 += recall_at_k(texts, gold, 3)
        r5 += recall_at_k(texts, gold, 5)
        mrr += reciprocal_rank(texts, gold)

        ans, _, ms = engine.query(q["question"], top_k=top_k)
        rag_lat.append(ms)
        rag_kw.append(keyword_hit(ans.text, q["answer_keywords"]))
        cp = citation_precision([c.text for c in ans.citations], gold)
        if cp is not None:
            rag_cp.append(cp)

        res, _, ms2 = engine.agent(q["question"], max_steps=max_steps)
        agent_lat.append(ms2)
        ag_kw.append(keyword_hit(res.answer, q["answer_keywords"]))
        cp2 = citation_precision([c.text for c in res.citations], gold)
        if cp2 is not None:
            ag_cp.append(cp2)
        ag_steps.append(len(res.steps))
        total_turns = len(res.steps) + res.parse_failures
        ag_valid.append((len(res.steps) / total_turns) if total_turns else 0.0)
        ag_fb += int(res.fallback_used)
        per_q.append({
            "id": q["id"], "kind": q["kind"], "recall@5": recall_at_k(texts, gold, 5),
            "rag_keyword_hit": rag_kw[-1], "agent_keyword_hit": ag_kw[-1],
            "agent_steps": len(res.steps), "agent_fallback": res.fallback_used,
            "rag_answer": ans.text, "agent_answer": res.answer,
        })
        log(f"[{i}/{len(questions)}] {q['id']} r@5={per_q[-1]['recall@5']:.0f} rag={int(rag_kw[-1])} "
            f"agent={int(ag_kw[-1])} steps={len(res.steps)} fb={int(res.fallback_used)} "
            f"({ms / 1000:.1f}s / {ms2 / 1000:.1f}s)")

    n = len(questions)
    return {
        "n_questions": n,
        "retrieval": {"recall@1": r1 / n, "recall@3": r3 / n, "recall@5": r5 / n, "mrr": mrr / n,
                      "p50_ms": percentile(retr_lat, 50), "p95_ms": percentile(retr_lat, 95)},
        "rag": {"keyword_hit_rate": sum(rag_kw) / n,
                "citation_precision": statistics.mean(rag_cp) if rag_cp else None,
                "p50_ms": percentile(rag_lat, 50), "p95_ms": percentile(rag_lat, 95)},
        "agent": {"keyword_hit_rate": sum(ag_kw) / n,
                  "citation_precision": statistics.mean(ag_cp) if ag_cp else None,
                  "tool_call_validity": statistics.mean(ag_valid), "mean_steps": statistics.mean(ag_steps),
                  "fallback_rate": ag_fb / n, "p50_ms": percentile(agent_lat, 50), "p95_ms": percentile(agent_lat, 95)},
        "per_question": per_q,
    }


def render_report(results: dict) -> str:
    r, g, a, m = results["retrieval"], results["rag"], results["agent"], results["meta"]

    def pct(x):
        return "n/a" if x is None else f"{100 * x:.1f}%"

    by_kind: dict[str, list[dict]] = {}
    for q in results["per_question"]:
        by_kind.setdefault(q["kind"], []).append(q)
    kind_rows = "\n".join(
        f"| {k} | {len(v)} | {pct(sum(q['recall@5'] for q in v) / len(v))} | "
        f"{pct(sum(q['rag_keyword_hit'] for q in v) / len(v))} | {pct(sum(q['agent_keyword_hit'] for q in v) / len(v))} |"
        for k, v in sorted(by_kind.items())
    )
    return f"""# Evaluation

Generated {m['generated_at']} by `python -m docagent.eval` on {m['machine']} ({m['device']}).
Provider: `{m['provider']}`. Embeddings: `{m['embedding_model']}`. Reranker: `{m['reranker_model']}`. Vector backend: `{m['vector_backend']}`.
Corpus: {m['n_docs']} synthetic handbook documents in `eval/corpus/` ({m['n_chunks']} chunks), {results['n_questions']} hand-written questions in `eval/questions.jsonl`.
Everything here is reproducible by cloning the repo and running the command above. Latencies are single-process on the machine named, not a production SLA.

## Retrieval (hybrid dense + BM25, cross-encoder rerank)

| recall@1 | recall@3 | recall@5 | MRR | p50 | p95 |
|---|---|---|---|---|---|
| {pct(r['recall@1'])} | {pct(r['recall@3'])} | {pct(r['recall@5'])} | {r['mrr']:.3f} | {r['p50_ms']:.0f} ms | {r['p95_ms']:.0f} ms |

## Answers

| Mode | keyword hit rate | citation precision | p50 | p95 |
|---|---|---|---|---|
| RAG (single pass) | {pct(g['keyword_hit_rate'])} | {pct(g['citation_precision'])} | {g['p50_ms'] / 1000:.1f} s | {g['p95_ms'] / 1000:.1f} s |
| Agent (ReAct) | {pct(a['keyword_hit_rate'])} | {pct(a['citation_precision'])} | {a['p50_ms'] / 1000:.1f} s | {a['p95_ms'] / 1000:.1f} s |

Agent tool-call validity: {pct(a['tool_call_validity'])}. Mean steps: {a['mean_steps']:.2f}. Fallback to plain RAG: {pct(a['fallback_rate'])} of runs.

## By question kind

| kind | n | recall@5 | RAG hit | Agent hit |
|---|---|---|---|---|
{kind_rows}

## How to read this

- *keyword hit rate*: all expected keywords appear in the answer. A strict proxy for correctness; it under-counts paraphrases.
- *citation precision*: fraction of cited chunks that contain the gold passage.
- *tool-call validity*: valid JSON tool calls / all model turns in agent mode.
- *fallback*: the agent gave up (two unparseable turns, step budget, or empty answer) and the question was answered by single-pass RAG instead. Fallback runs still count toward the agent's hit rate.
- The generation model is a 1.5B-parameter local model; these numbers describe this configuration only.
"""


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data-dir", default="data-eval")
    ap.add_argument("--provider", default="hf", choices=["hf", "anthropic", "fake"])
    ap.add_argument("--out", default="eval/results.json")
    ap.add_argument("--report", default="docs/EVAL.md")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--max-steps", type=int, default=6)
    args = ap.parse_args(argv)

    engine = build_engine(Path(args.data_dir), args.provider)
    questions = load_questions(args.limit)
    results = evaluate(engine, questions, args.top_k, args.max_steps)
    try:
        from docagent.llm.hf_local import pick_device

        device = pick_device()
    except Exception:
        device = "cpu"
    results["meta"] = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "machine": f"{platform.machine()} {platform.system()}",
        "device": device,
        "provider": getattr(engine.provider, "name", args.provider),
        "embedding_model": engine.settings.embedding_model,
        "reranker_model": engine.settings.reranker_model,
        "vector_backend": engine.settings.vector_backend,
        "n_docs": len(engine.store.list_documents()),
        "n_chunks": engine.store.count_ready_chunks(),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2))
    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(render_report(results))
    print(json.dumps({k: v for k, v in results.items() if k != "per_question"}, indent=2))
    return results


if __name__ == "__main__":
    main()
