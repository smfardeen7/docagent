import sys

from docagent.settings import Settings


def test_defaults_and_env_prefix(monkeypatch, tmp_path):
    monkeypatch.setenv("DOCAGENT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DOCAGENT_TOP_K", "3")
    s = Settings()
    assert s.data_dir == tmp_path
    assert s.top_k == 3
    assert s.chunk_tokens == 256 and s.chunk_overlap == 32
    assert s.provider == "hf"
    assert s.index_dir == tmp_path / "index"
    assert s.raw_dir == tmp_path / "raw"
    assert s.db_path == tmp_path / "docagent.db"


def test_vector_backend_defaults_per_platform_and_overrides(monkeypatch):
    assert Settings().vector_backend == ("numpy" if sys.platform == "darwin" else "faiss")
    monkeypatch.setenv("DOCAGENT_VECTOR_BACKEND", "numpy")
    assert Settings().vector_backend == "numpy"
