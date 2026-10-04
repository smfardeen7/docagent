import re
from dataclasses import dataclass

from docagent.llm.base import LLMProvider
from docagent.retrieve.retriever import Hit, Retriever

from .prompt import build_rag_messages

CITATION_RE = re.compile(r"\[(\d+)\]")
NO_HITS_TEXT = "I could not find anything relevant in the indexed documents."


@dataclass(frozen=True)
class Citation:
    n: int
    chunk_id: int
    doc_id: str
    ordinal: int
    text: str


@dataclass
class Answer:
    text: str
    citations: list[Citation]
    hits: list[Hit]


def parse_citations(text: str, hits: list[Hit]) -> list[Citation]:
    """Map `[n]` markers in the answer back to the hits they refer to; drops duplicates and out-of-range numbers."""
    seen: set[int] = set()
    out: list[Citation] = []
    for m in CITATION_RE.finditer(text):
        n = int(m.group(1))
        if n in seen or not (1 <= n <= len(hits)):
            continue
        seen.add(n)
        h = hits[n - 1]
        out.append(Citation(n, h.chunk_id, h.doc_id, h.ordinal, h.text))
    return out


def answer_question(question: str, retriever: Retriever, provider: LLMProvider, top_k: int = 5,
                    max_new_tokens: int = 384) -> Answer:
    hits = retriever.search(question, top_k=top_k)
    if not hits:
        return Answer(NO_HITS_TEXT, [], [])
    text = provider.generate(build_rag_messages(question, hits), max_new_tokens=max_new_tokens)
    return Answer(text, parse_citations(text, hits), hits)
