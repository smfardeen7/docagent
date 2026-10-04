import json

from docagent.agent import build_default_tools, run_agent
from docagent.agent.loop import extract_chunk_ids
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


def test_extract_chunk_ids_from_tool_observations():
    assert extract_chunk_ids("chunk_id=7 doc=d score=0.1: x\nchunk_id=9 doc=d: y") == [7, 9]
    assert extract_chunk_ids("[chunk 3] a\n[chunk 4] b\n[chunk 3] again") == [3, 4]
    assert extract_chunk_ids("no results") == []


def test_scripted_run_gathers_evidence_then_synthesizes_grounded_answer(tmp_path):
    store, reg = setup(tmp_path)
    p = FakeProvider([
        call("search_docs", query="meals", k=2),
        call("calculate", expression="40*3"),
        call("final_answer", answer="whatever the model wrote", citations=[1]),
        "Three days of meals is 120 dollars [1].",  # grounded synthesis over the gathered evidence
    ])
    r = run_agent("How much for three days of meals?", reg, p, FakeRetriever(), store, max_steps=6)
    assert r.fallback_used is False and r.parse_failures == 0
    assert [s.tool for s in r.steps] == ["search_docs", "calculate", "final_answer"]
    assert r.steps[1].observation == "120"
    assert r.answer == "Three days of meals is 120 dollars [1]."
    assert [c.chunk_id for c in r.citations] == [1]
    synthesis_prompt = p.calls[-1][-1].content
    assert "Sources:" in synthesis_prompt and "[1] Meals up to forty dollars per day." in synthesis_prompt
    assert "40*3 = 120" in synthesis_prompt
    # observations are fed back as user messages during gathering
    assert any(m.role == "user" and m.content.startswith("Observation:") for m in p.calls[1])


def test_cited_chunks_come_first_then_observed_ones(tmp_path):
    store, reg = setup(tmp_path)
    p = FakeProvider([
        call("search_docs", query="meals", k=2),  # observes chunks 1 and 2
        call("final_answer", answer="x", citations=[2, 999, "bad", True]),
        "Receipts are needed over 25 [1]; meals are forty [2].",
    ])
    r = run_agent("q", reg, p, FakeRetriever(), store)
    assert [c.chunk_id for c in r.citations] == [2, 1]
    assert "[1] Receipts over 25." in p.calls[-1][-1].content


def test_read_chunk_observations_count_as_evidence(tmp_path):
    store, reg = setup(tmp_path)
    p = FakeProvider([call("read_chunk", chunk_id=2), call("final_answer", answer="", citations=[]), "Over 25 [1]."])
    r = run_agent("q", reg, p, FakeRetriever(), store)
    assert r.fallback_used is False and [c.chunk_id for c in r.citations] == [1]
    assert "[1] Meals up to forty dollars per day." in p.calls[-1][-1].content  # neighbours of chunk 2 include chunk 1


def test_final_answer_without_any_evidence_falls_back(tmp_path):
    store, reg = setup(tmp_path)
    p = FakeProvider([call("final_answer", answer="guess", citations=[]), "fallback [1]"])
    r = run_agent("q", reg, p, FakeRetriever(), store)
    assert r.fallback_used is True and r.answer == "fallback [1]"


def test_two_parse_failures_fall_back_to_rag(tmp_path):
    store, reg = setup(tmp_path)
    p = FakeProvider(["I think I should search", "still no json", "Meals are forty dollars [1]."])
    r = run_agent("meals?", reg, p, FakeRetriever(), store, max_steps=6)
    assert r.fallback_used is True and r.parse_failures == 2
    assert r.citations[0].chunk_id == 1


def test_one_failure_then_recovery_is_not_fallback(tmp_path):
    store, reg = setup(tmp_path)
    p = FakeProvider(["oops", call("search_docs", query="m"), call("final_answer", answer="ok", citations=[]), "ok [1]"])
    r = run_agent("q", reg, p, FakeRetriever(), store)
    assert r.fallback_used is False and r.parse_failures == 1 and r.answer == "ok [1]"


def test_max_steps_exhausted_falls_back(tmp_path):
    store, reg = setup(tmp_path)
    p = FakeProvider([call("search_docs", query="x")] * 3 + ["fallback answer [1]"])
    r = run_agent("q", reg, p, FakeRetriever(), store, max_steps=3)
    assert r.fallback_used is True and len(r.steps) == 3


def test_empty_synthesis_falls_back(tmp_path):
    store, reg = setup(tmp_path)
    p = FakeProvider([call("search_docs", query="m"), call("final_answer", answer="x", citations=[1]), "   ", "fallback [1]"])
    r = run_agent("q", reg, p, FakeRetriever(), store)
    assert r.fallback_used is True and r.answer == "fallback [1]"


def test_on_step_callback_receives_each_step(tmp_path):
    store, reg = setup(tmp_path)
    seen = []
    p = FakeProvider([call("calculate", expression="1+1"), call("search_docs", query="q"), call("final_answer", answer="2", citations=[]), "2 [1]"])
    run_agent("q", reg, p, FakeRetriever(), store, on_step=seen.append)
    assert [s.tool for s in seen] == ["calculate", "search_docs", "final_answer"]
