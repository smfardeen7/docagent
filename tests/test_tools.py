import pytest

from docagent.agent.calc import safe_calculate
from docagent.agent.tools import build_default_tools
from docagent.ingest.chunker import Chunk
from docagent.retrieve import Hit
from docagent.store import Store


def test_calc_arithmetic():
    assert safe_calculate("40 * 3 + 2.5") == "122.5"
    assert safe_calculate("(10 - 4) / 3") == "2"


@pytest.mark.parametrize("expr", ["__import__('os')", "open('x')", "a + 1", "2 ** 999999", "1; 2", "[1,2]", "1/0"])
def test_calc_rejects_unsafe(expr):
    assert safe_calculate(expr).startswith("error:")


class FakeRetriever:
    def search(self, q, top_k=5):
        return [Hit(1, "d1", 0, "Meals up to forty dollars.", 0.9)][:top_k]


def test_registry_calls_and_describe(tmp_path):
    store = Store(tmp_path / "t.db")
    store.create_document("d1", "h.md")
    store.add_chunks("d1", [Chunk(0, "Meals up to forty dollars.", 5), Chunk(1, "Receipts over 25.", 4)])
    reg = build_default_tools(FakeRetriever(), store)
    assert set(reg.names()) == {"search_docs", "read_chunk", "compare", "calculate"}
    assert "search_docs" in reg.describe() and "chunk_id" in reg.describe() and "final_answer" in reg.describe()
    out = reg.call("search_docs", {"query": "meals", "k": 1})
    assert "chunk_id=1" in out and "forty dollars" in out
    assert "Receipts over 25." in reg.call("read_chunk", {"chunk_id": 1})
    assert "[chunk 2]" in reg.call("compare", {"chunk_ids": [1, 2]})
    assert reg.call("calculate", {"expression": "40*5"}) == "200"
    assert reg.call("nope", {}).startswith("error: unknown tool")
    assert reg.call("read_chunk", {"chunk_id": 999}).startswith("error:")
    assert reg.call("read_chunk", {}).startswith("error:")
    assert reg.call("read_chunk", "not-a-dict").startswith("error:")
    assert reg.call("read_chunk", {"chunk_id": "abc"}).startswith("error:")
