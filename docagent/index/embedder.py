import hashlib
import re
from typing import Protocol

import numpy as np

BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class Embedder(Protocol):
    dim: int

    def encode(self, texts: list[str]) -> np.ndarray: ...

    def encode_query(self, text: str) -> np.ndarray: ...


def _normalize(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (m / norms).astype(np.float32)


class HashEmbedder:
    """Deterministic bag-of-words hashing embedder for tests. No model download."""

    def __init__(self, dim: int = 64):
        self.dim = dim

    def encode(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            for tok in re.findall(r"\w+", t.lower()):
                h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
                out[i, h % self.dim] += 1.0
        return _normalize(out)

    def encode_query(self, text: str) -> np.ndarray:
        return self.encode([text])[0]


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str, batch_size: int = 32):
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        get_dim = getattr(self._model, "get_embedding_dimension", None) or self._model.get_sentence_embedding_dimension
        self.dim = int(get_dim())
        self.batch_size = batch_size
        self._query_prefix = BGE_QUERY_PREFIX if "bge" in model_name.lower() else ""

    def encode(self, texts: list[str]) -> np.ndarray:
        vecs = self._model.encode(texts, batch_size=self.batch_size, normalize_embeddings=True, convert_to_numpy=True)
        return np.asarray(vecs, dtype=np.float32)

    def encode_query(self, text: str) -> np.ndarray:
        return self.encode([self._query_prefix + text])[0]
