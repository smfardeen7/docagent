"""Exact inner-product vector index with two interchangeable backends.

`faiss` is the default on Linux (containers, CI). On macOS, faiss-cpu and torch each bundle their own
OpenMP runtime and the process aborts when both load, so the pure-NumPy backend is the default there.
Both backends are exact flat search over L2-normalized vectors and return identical rankings.
"""

import os
import sys
from pathlib import Path
from typing import Protocol

import numpy as np

BACKENDS = ("numpy", "faiss")
FAISS_FILE = "faiss.index"
NUMPY_FILE = "vectors.npz"


def default_backend() -> str:
    return "numpy" if sys.platform == "darwin" else "faiss"


class _Backend(Protocol):
    def __len__(self) -> int: ...

    def add(self, ids: np.ndarray, vectors: np.ndarray) -> None: ...

    def search(self, query: np.ndarray, k: int) -> list[tuple[int, float]]: ...

    def save(self, directory: Path) -> None: ...


class _NumpyFlat:
    def __init__(self, dim: int, ids: np.ndarray | None = None, vecs: np.ndarray | None = None):
        self.dim = dim
        self._ids = ids if ids is not None else np.zeros(0, dtype=np.int64)
        self._vecs = vecs if vecs is not None else np.zeros((0, dim), dtype=np.float32)

    def __len__(self) -> int:
        return int(self._ids.shape[0])

    def add(self, ids: np.ndarray, vectors: np.ndarray) -> None:
        self._ids = np.concatenate([self._ids, ids])
        self._vecs = np.vstack([self._vecs, vectors])

    def search(self, query: np.ndarray, k: int) -> list[tuple[int, float]]:
        scores = self._vecs @ query
        top = np.argsort(-scores)[:k]
        return [(int(self._ids[i]), float(scores[i])) for i in top]

    def save(self, directory: Path) -> None:
        tmp = directory / (NUMPY_FILE + ".tmp")
        with open(tmp, "wb") as f:
            np.savez(f, ids=self._ids, vecs=self._vecs)
        os.replace(tmp, directory / NUMPY_FILE)

    @classmethod
    def load(cls, directory: Path, dim: int) -> "_NumpyFlat":
        path = directory / NUMPY_FILE
        if not path.exists():
            return cls(dim)
        with np.load(path) as data:
            return cls(dim, data["ids"].astype(np.int64), data["vecs"].astype(np.float32))


class _FaissFlat:
    def __init__(self, dim: int, index=None):
        import faiss

        self._faiss = faiss
        self.dim = dim
        self._index = index or faiss.IndexIDMap2(faiss.IndexFlatIP(dim))

    def __len__(self) -> int:
        return int(self._index.ntotal)

    def add(self, ids: np.ndarray, vectors: np.ndarray) -> None:
        self._index.add_with_ids(np.ascontiguousarray(vectors), ids)

    def search(self, query: np.ndarray, k: int) -> list[tuple[int, float]]:
        scores, ids = self._index.search(np.ascontiguousarray(query.reshape(1, -1)), k)
        return [(int(i), float(s)) for i, s in zip(ids[0], scores[0]) if i != -1]

    def save(self, directory: Path) -> None:
        tmp = directory / (FAISS_FILE + ".tmp")
        self._faiss.write_index(self._index, str(tmp))
        os.replace(tmp, directory / FAISS_FILE)

    @classmethod
    def load(cls, directory: Path, dim: int) -> "_FaissFlat":
        import faiss

        path = directory / FAISS_FILE
        if not path.exists():
            return cls(dim)
        return cls(dim, faiss.read_index(str(path)))


class VectorIndex:
    def __init__(self, dim: int, backend: str | None = None, _impl: _Backend | None = None):
        backend = backend or default_backend()
        if backend not in BACKENDS:
            raise ValueError(f"unknown vector backend {backend!r}; choose one of {BACKENDS}")
        self.dim = dim
        self.backend = backend
        self._impl = _impl or (_NumpyFlat(dim) if backend == "numpy" else _FaissFlat(dim))

    def __len__(self) -> int:
        return len(self._impl)

    def add(self, ids: list[int], vectors: np.ndarray) -> None:
        if len(ids) == 0:
            return
        vecs = np.ascontiguousarray(vectors, dtype=np.float32)
        if vecs.shape != (len(ids), self.dim):
            raise ValueError(f"expected vectors of shape ({len(ids)}, {self.dim}), got {vecs.shape}")
        self._impl.add(np.asarray(ids, dtype=np.int64), vecs)

    def search(self, vector: np.ndarray, k: int) -> list[tuple[int, float]]:
        if len(self) == 0 or k <= 0:
            return []
        q = np.ascontiguousarray(vector, dtype=np.float32).reshape(-1)
        return self._impl.search(q, min(k, len(self)))

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self._impl.save(directory)

    @classmethod
    def load(cls, directory: Path, dim: int, backend: str | None = None) -> "VectorIndex":
        backend = backend or default_backend()
        if backend not in BACKENDS:
            raise ValueError(f"unknown vector backend {backend!r}; choose one of {BACKENDS}")
        impl = _NumpyFlat.load(directory, dim) if backend == "numpy" else _FaissFlat.load(directory, dim)
        return cls(dim, backend, _impl=impl)
