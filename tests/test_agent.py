import json

from docagent.agent import build_default_tools, run_agent
from docagent.ingest.chunker import Chunk
from docagent.llm import FakeProvider
from docagent.retrieve import Hit
from docagent.store import Store


class FakeRetriever:
    def search(self, q, top_k=5):
        return [
            Hit(1, "d1", 0, "Meals up to forty dollars per day.", 0.9),
            Hit(2, "d1", 1, "Receipts over 25.", 0.4),
        ][:top_k]


def setup(tmp_path):
    store = Store(tmp_path / "t.db")
    store.create_document("d1", "h.md")
    store.add_chunks("d1", [Chunk(0, "Meals up to forty dollars per day.", 6), Chunk(1, "Receipts over 25.", 4)])
    store.set_document_status("d1", "ready", n_chunks=2)
    return store, build_default_tools(FakeRetriever(), store)


def call(tool, **args):
    return json.dumps({"thought": "t", "tool": tool, "args": args})


def test_scripted_run_completes_with_trace(tmp_path):
    store, reg = setup(tmp_path)
    p = FakeProvider([
        call("search_docs", query="meals", k=2),
        call("calculate", expression="40*3"),
        call("final_answer", answer="Three days of meals is 120 dollars.", citations=[1]),
    ])
    r = run_agent("How much for three days of meals?", reg, p, FakeRetriever(), store, max_steps=6)
    assert r.fallback_used is False and r.parse_failures == 0
    assert [s.tool for s in r.steps] == ["search_docs", "calculate", "final_answer"]
    assert r.steps[1].observation == "120"
    assert r.citations[0].chunk_id == 1 and r.answer.startswith("Three days")
    # the observation is fed back to the model as a user message
    assert any(m.role == "user" and m.content.startswith("Observation:") for m in p.calls[1])


def test_two_parse_failures_fall_back_to_rag(tmp_path):
    store, reg = setup(tmp_path)
    p = FakeProvider(["I think I should search", "still no json", "Meals are forty dollars [1]."])
    r = run_agent("meals?", reg, p, FakeRetriever(), store, max_steps=6)
    assert r.fallback_used is True and r.parse_failures == 2
    assert r.citations[0].chunk_id == 1


def test_one_failure_then_recovery_is_not_fallback(tmp_path):
    store, reg = setup(tmp_path)
    p = FakeProvider(["oops", call("final_answer", answer="ok", citations=[])])
    r = run_agent("q", reg, p, FakeRetriever(), store)
    assert r.fallback_used is False and r.parse_failures == 1 and r.answer == "ok"


def test_max_steps_exhausted_falls_back(tmp_path):
    store, reg = setup(tmp_path)
    p = FakeProvider([call("search_docs", query="x")] * 3 + ["fallback answer [1]"])
    r = run_agent("q", reg, p, FakeRetriever(), store, max_steps=3)
    assert r.fallback_used is True and len(r.steps) == 3


def test_invalid_citation_ids_dropped(tmp_path):
    store, reg = setup(tmp_path)
    p = FakeProvider([call("final_answer", answer="a", citations=[2, 999, "bad", True])])
    r = run_agent("q", reg, p, FakeRetriever(), store)
    assert [c.chunk_id for c in r.citations] == [2]


def test_empty_final_answer_falls_back(tmp_path):
    store, reg = setup(tmp_path)
    p = FakeProvider([call("final_answer", answer="   ", citations=[1]), "fallback [1]"])
    r = run_agent("q", reg, p, FakeRetriever(), store)
    assert r.fallback_used is True and r.answer == "fallback [1]"


def test_on_step_callback_receives_each_step(tmp_path):
    store, reg = setup(tmp_path)
    seen = []
    p = FakeProvider([call("calculate", expression="1+1"), call("final_answer", answer="2", citations=[])])
    run_agent("q", reg, p, FakeRetriever(), store, on_step=seen.append)
    assert [s.tool for s in seen] == ["calculate", "final_answer"]
