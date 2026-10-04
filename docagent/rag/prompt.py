from docagent.llm.base import Message
from docagent.retrieve.retriever import Hit

SYSTEM = (
    "You answer questions using only the numbered sources provided. "
    "Cite every claim with the source number in square brackets like [n]. "
    "If the sources do not contain the answer, say so plainly and do not guess. "
    "Keep answers concise."
)


def build_rag_messages(question: str, hits: list[Hit]) -> list[Message]:
    sources = "\n\n".join(f"[{i}] {h.text}" for i, h in enumerate(hits, start=1))
    user = f"Sources:\n\n{sources}\n\nQuestion: {question}"
    return [Message("system", SYSTEM), Message("user", user)]
