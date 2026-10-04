import json
from collections.abc import Callable
from dataclasses import dataclass, field

from docagent.llm.base import LLMProvider, Message
from docagent.rag.answer import Citation, answer_question
from docagent.retrieve.retriever import Retriever
from docagent.store import Store

from .parser import ParseError, parse_tool_call
from .prompt import build_agent_system_prompt
from .tools import ToolRegistry

MAX_OBSERVATION_CHARS = 2000


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


def _citations_from_ids(ids: object, store: Store) -> list[Citation]:
    clean: list[int] = []
    for i in ids if isinstance(ids, list) else []:
        if isinstance(i, int) and not isinstance(i, bool) and i not in clean:
            clean.append(i)
    rows = store.get_chunks(clean)
    return [Citation(n, r["id"], r["doc_id"], r["ordinal"], r["text"]) for n, r in enumerate(rows, start=1)]


def run_agent(question: str, registry: ToolRegistry, provider: LLMProvider, retriever: Retriever, store: Store,
              max_steps: int = 6, max_new_tokens: int = 384,
              on_step: Callable[[Step], None] | None = None) -> AgentResult:
    """ReAct loop. Two consecutive unparseable turns, an exhausted step budget, or an empty final answer
    fall back to single-pass RAG; the result says so via fallback_used."""
    messages = [Message("system", build_agent_system_prompt(registry)), Message("user", f"Question: {question}")]
    steps: list[Step] = []
    parse_failures = 0
    consecutive_failures = 0

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
            answer = str(call.args.get("answer", "")).strip()
            citations = _citations_from_ids(call.args.get("citations", []), store)
            step = Step(n, call.thought, call.tool, call.args, "done")
            steps.append(step)
            if on_step:
                on_step(step)
            if answer:
                return AgentResult(answer, citations, steps, False, parse_failures)
            break

        observation = registry.call(call.tool, call.args)[:MAX_OBSERVATION_CHARS]
        step = Step(n, call.thought, call.tool, call.args, observation)
        steps.append(step)
        if on_step:
            on_step(step)
        messages.append(Message("assistant", json.dumps({"thought": call.thought, "tool": call.tool, "args": call.args})))
        messages.append(Message("user", f"Observation: {observation}"))

    fallback = answer_question(question, retriever, provider, max_new_tokens=max_new_tokens)
    return AgentResult(fallback.text, fallback.citations, steps, True, parse_failures)
