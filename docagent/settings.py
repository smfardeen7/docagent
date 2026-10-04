from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DOCAGENT_", env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    generation_model: str = "Qwen/Qwen2.5-1.5B-Instruct"
    provider: Literal["hf", "anthropic", "fake"] = "hf"
    anthropic_model: str = "claude-sonnet-5-5"
    redis_url: str = "redis://localhost:6379"
    chunk_tokens: int = 256
    chunk_overlap: int = 32
    dense_k: int = 20
    bm25_k: int = 20
    rerank_k: int = 10
    top_k: int = 5
    max_steps: int = 6
    max_new_tokens: int = 384
    max_upload_bytes: int = 20 * 1024 * 1024

    @property
    def index_dir(self) -> Path:
        return self.data_dir / "index"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "docagent.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
