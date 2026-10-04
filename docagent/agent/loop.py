"""ReAct agent: the model gathers evidence with tools, then the answer is synthesized from that evidence.

The loop runs the model turn by turn. Each turn must be one JSON tool call. `search_docs`, `read_chunk` and
`compare` observations contribute chunks to an evidence set; `calculate` observations are kept as computed
values. When the model calls `final_answer`, the answer is NOT taken from the model's free text: it is generated
with the cited-sources RAG prompt over the gathered chunks (cited ones first), with computed values appended to
the question. This keeps small models honest — the measured gap between free-form agent answers and grounded
synthesis was the reason for this design (see docs/EVAL.md).

Fallback to single-pass RAG, flagged `fallback_used=True`, happens on: two consecutive unparseable turns, an
exhausted step budget, `final_answer` with no evidence gathered, or an empty synthesis.
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from docagent.llm.base import LLMProvider, Message
from docagent.rag.answer import Citation, answer_question, parse_citations
from docagent.rag.prompt import build_rag_messages
from docagent.retrieve.retriever import Hit, Retriever
from docagent.store import Store

from .parser import ParseError, parse_tool_call
from .prompt import build_agent_system_prompt
from .tools import ToolRegistry

MAX_OBSERVATION_CHARS = 4000
MAX_EVIDENCE_CHUNKS = 8
EVIDENCE_TOOLS = {"search_docs", "read_chunk", "compare"}
_CHUNK_ID_RE = re.compile(r"(?:chunk_id=|\[chunk )(\d+)")


@dataclass
class Step:
    n: int
    thought: str
    tool: str
    args: dict
    observation: str


@dataclass
class AgentResult:
    answer: str
    citations: list[Citation]
    steps: list[Step] = field(default_factory=list)
    fallback_used: bool = False
    parse_failures: int = 0


def extract_chunk_ids(observation: str) -> list[int]:
    """Chunk ids mentioned in a tool observation, in first-seen order."""
    seen: list[int] = []
    for m in _CHUNK_ID_RE.finditer(observation):
        i = int(m.group(1))
        if i not in seen:
            seen.append(i)
    return seen


def _clean_ids(ids: object) -> list[int]:
    clean: list[int] = []
    for i in ids if isinstance(ids, list) else []:
        if isinstance(i, int) and not isinstance(i, bool) and i not in clean:
            clean.append(i)
    return clean


def _synthesize(question: str, evidence_ids: list[int], computed: list[str], store: Store, provider: LLMProvider,
                max_new_tokens: int) -> tuple[str, list[Citation]] | None:
    rows = store.get_chunks(evidence_ids[:MAX_EVIDENCE_CHUNKS])
    if not rows:
        return None
    hits = [Hit(r["id"], r["doc_id"], r["ordinal"], r["text"], 0.0) for r in rows]
    q = question if not computed else f"{question}\n\nComputed values: " + "; ".join(computed)
    text = provider.generate(build_rag_messages(q, hits), max_new_tokens=max_new_tokens).strip()
    if not text:
        return None
    return text, parse_citations(text, hits)


def _evidence_order(cited: list[int], observed: list[int]) -> list[int]:
    """Cited ids the model actually saw come first; then the newest observations fill the remaining slots."""
    cited_seen = [i for i in cited if i in observed]
    rest = [i for i in observed if i not in cited_seen]
    room = MAX_EVIDENCE_CHUNKS - len(cited_seen)
    return cited_seen + (rest[-room:] if room > 0 else [])


def run_agent(question: str, registry: ToolRegistry, provider: LLMProvider, retriever: Retriever, store: Store,
              max_steps: int = 6, max_new_tokens: int = 384, top_k: int = 5,
              on_step: Callable[[Step], None] | None = None) -> AgentResult:
    messages = [Message("system", build_agent_system_prompt(registry)), Message("user", f"Question: {question}")]
    steps: list[Step] = []
    observed: list[int] = []
    computed: list[str] = []
    parse_failures = 0
    consecutive_failures = 0

    def record(step: Step) -> None:
        steps.append(step)
        if on_step:
            on_step(step)

    for n in range(1, max_steps + 1):
        raw = provider.generate(messages, max_new_tokens=max_new_tokens)
        try:
            call = parse_tool_call(raw)
        except ParseError as e:
            parse_failures += 1
            consecutive_failures += 1
            if consecutive_failures >= 2:
                break
            messages.append(Message("assistant", raw))
            messages.append(Message("user", f"Observation: error: {e}. Reply with exactly one JSON object."))
            continue
        consecutive_failures = 0

        if call.tool == "final_answer":
            record(Step(n, call.thought, call.tool, call.args, "done"))
            evidence = _evidence_order(_clean_ids(call.args.get("citations", [])), observed)
            result = _synthesize(question, evidence, computed, store, provider, max_new_tokens)
            if result is None:
                break
            text, citations = result
            return AgentResult(text, citations, steps, False, parse_failures)

        observation = registry.call(call.tool, call.args)[:MAX_OBSERVATION_CHARS]
        record(Step(n, call.thought, call.tool, call.args, observation))
        if call.tool in EVIDENCE_TOOLS:
            observed.extend(i for i in extract_chunk_ids(observation) if i not in observed)
        elif call.tool == "calculate" and not observation.startswith("error"):
            computed.append(f"{call.args.get('expression', '')} = {observation}")
        messages.append(Message("assistant", json.dumps({"thought": call.thought, "tool": call.tool, "args": call.args})))
        messages.append(Message("user", f"Observation: {observation}"))

    fallback = answer_question(question, retriever, provider, top_k=top_k, max_new_tokens=max_new_tokens)
    return AgentResult(fallback.text, fallback.citations, steps, True, parse_failures)
