import pytest

from docagent.ingest.chunker import get_tokenizer


@pytest.fixture(scope="session")
def tokenizer():
    return get_tokenizer("BAAI/bge-small-en-v1.5")
