import json
from collections.abc import Callable
from dataclasses import dataclass, field

from docagent.retrieve.retriever import Retriever
from docagent.store import Store

from .calc import safe_calculate


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    fn: Callable[..., str]


@dataclass
class ToolRegistry:
    _tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def describe(self) -> str:
        lines = [f"- {t.name}: {t.description} args={json.dumps(t.parameters)}" for t in self._tools.values()]
        lines.append('- final_answer: finish with your answer. args={"answer": "string", "citations": [chunk_id, ...]}')
        return "\n".join(lines)

    def call(self, name: str, args: dict) -> str:
        """Run a tool. Tools never raise into the agent loop; failures come back as 'error: ...' observations."""
        tool = self.get(name)
        if tool is None:
            return f"error: unknown tool '{name}'"
        if not isinstance(args, dict):
            return "error: args must be an object"
        try:
            return tool.fn(**args)
        except TypeError as e:
            return f"error: bad arguments for {name}: {e}"
        except Exception as e:
            return f"error: {type(e).__name__}: {e}"


def build_default_tools(retriever: Retriever, store: Store) -> ToolRegistry:
    reg = ToolRegistry()

    def search_docs(query: str, k: int = 5) -> str:
        hits = retriever.search(str(query), top_k=max(1, min(int(k), 10)))
        if not hits:
            return "no results"
        return "\n".join(f"chunk_id={h.chunk_id} doc={h.doc_id} score={h.score:.3f}: {h.text[:300]}" for h in hits)

    def read_chunk(chunk_id: int) -> str:
        rows = store.neighbors(int(chunk_id))
        if not rows:
            return f"error: chunk {chunk_id} not found"
        return "\n".join(f"[chunk {r['id']}] {r['text']}" for r in rows)

    def compare(chunk_ids: list[int]) -> str:
        rows = store.get_chunks([int(i) for i in chunk_ids][:6])
        if not rows:
            return "error: no such chunks"
        return "\n\n".join(f"[chunk {r['id']}] {r['text']}" for r in rows)

    def calculate(expression: str) -> str:
        return safe_calculate(str(expression))

    reg.register(Tool("search_docs", "Search the indexed documents.", {"query": "string", "k": "integer (1-10)"}, search_docs))
    reg.register(Tool("read_chunk", "Read a chunk with its neighbours.", {"chunk_id": "integer"}, read_chunk))
    reg.register(Tool("compare", "Show several chunks side by side.", {"chunk_ids": "[integer]"}, compare))
    reg.register(Tool("calculate", "Evaluate arithmetic.", {"expression": "string"}, calculate))
    return reg
