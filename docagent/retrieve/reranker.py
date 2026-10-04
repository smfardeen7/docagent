from typing import Protocol

from docagent.index.bm25_index import tokenize


class Reranker(Protocol):
    def score(self, query: str, texts: list[str]) -> list[float]: ...


class LexicalReranker:
    """Jaccard token overlap. Deterministic, for tests and offline fallback."""

    def score(self, query: str, texts: list[str]) -> list[float]:
        q = set(tokenize(query))
        out = []
        for t in texts:
            s = set(tokenize(t))
            out.append(len(q & s) / len(q | s) if (q | s) else 0.0)
        return out


class CrossEncoderReranker:
    def __init__(self, model_name: str):
        from sentence_transformers import CrossEncoder

        self._model = CrossEncoder(model_name)

    def score(self, query: str, texts: list[str]) -> list[float]:
        if not texts:
            return []
        return [float(s) for s in self._model.predict([(query, t) for t in texts])]
