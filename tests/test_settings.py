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
