import os
import pickle
import re
from pathlib import Path

from rank_bm25 import BM25Okapi

_TOKEN_RE = re.compile(r"\w+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class BM25Index:
    """Sparse lexical index over chunk texts. Rebuilt from the store after each ingest (IDF needs the whole corpus)."""

    def __init__(self, ids: list[int], docs: list[list[str]]):
        self._ids = ids
        self._docs = docs
        self._bm25 = BM25Okapi(docs) if docs else None

    def __len__(self) -> int:
        return len(self._ids)

    @classmethod
    def build(cls, items: list[tuple[int, str]]) -> "BM25Index":
        return cls([i for i, _ in items], [tokenize(t) for _, t in items])

    def search(self, query: str, k: int) -> list[tuple[int, float]]:
        if self._bm25 is None or k <= 0:
            return []
        scores = self._bm25.get_scores(tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
        return [(self._ids[i], float(scores[i])) for i in order if scores[i] > 0]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "wb") as f:
            pickle.dump({"ids": self._ids, "docs": self._docs}, f)
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: Path) -> "BM25Index":
        if not path.exists():
            return cls([], [])
        with open(path, "rb") as f:
            d = pickle.load(f)
        return cls(d["ids"], d["docs"])
