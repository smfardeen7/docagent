import sys

import numpy as np
import pytest

from docagent.index.embedder import HashEmbedder
from docagent.index.vector_index import VectorIndex, default_backend

# faiss-cpu and torch each bundle their own libomp on macOS and abort the process when both load,
# so the faiss backend is exercised only where the two coexist (Linux CI).
BACKENDS = ["numpy"] + (["faiss"] if sys.platform != "darwin" else [])


def test_hash_embedder_is_deterministic_and_normalized():
    e = HashEmbedder(dim=32)
    a = e.encode(["expense policy meals", "expense policy meals"])
    assert a.shape == (2, 32) and a.dtype == np.float32
    assert np.allclose(a[0], a[1])
    assert abs(np.linalg.norm(a[0]) - 1.0) < 1e-5


def test_default_backend_matches_platform():
    assert default_backend() == ("numpy" if sys.platform == "darwin" else "faiss")


@pytest.mark.parametrize("backend", BACKENDS)
def test_index_add_search_save_load(tmp_path, backend):
    e = HashEmbedder(dim=32)
    idx = VectorIndex(dim=32, backend=backend)
    texts = ["meals forty dollars", "security badge policy", "parental leave weeks"]
    idx.add([10, 11, 12], e.encode(texts))
    hits = idx.search(e.encode_query("meals dollars"), k=2)
    assert hits[0][0] == 10 and len(hits) == 2
    assert hits[0][1] >= hits[1][1]
    idx.save(tmp_path)
    loaded = VectorIndex.load(tmp_path, dim=32, backend=backend)
    assert len(loaded) == 3
    assert loaded.search(e.encode_query("badge"), k=1)[0][0] == 11


@pytest.mark.parametrize("backend", BACKENDS)
def test_search_on_empty_index_returns_nothing(backend):
    idx = VectorIndex(dim=8, backend=backend)
    assert idx.search(np.zeros(8, dtype=np.float32), k=5) == []


def test_load_missing_dir_gives_empty_index(tmp_path):
    idx = VectorIndex.load(tmp_path / "nope", dim=8, backend="numpy")
    assert len(idx) == 0


def test_unknown_backend_rejected():
    with pytest.raises(ValueError):
        VectorIndex(dim=8, backend="annoy")
