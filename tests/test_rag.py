import pytest

from docagent.llm import FakeProvider, Message
from docagent.rag import Answer, answer_question, build_rag_messages, parse_citations
from docagent.retrieve import Hit

HITS = [Hit(7, "d1", 0, "Meals up to forty dollars.", 0.9), Hit(9, "d1", 2, "Leave is twelve weeks.", 0.5)]


def test_prompt_numbers_sources():
    msgs = build_rag_messages("meals?", HITS)
    assert msgs[0].role == "system" and "[n]" in msgs[0].content
    assert "[1] Meals up to forty dollars." in msgs[-1].content
    assert "[2] Leave is twelve weeks." in msgs[-1].content
    assert msgs[-1].content.rstrip().endswith("meals?")


def test_parse_citations_dedup_and_ignore_invalid():
    cits = parse_citations("Forty dollars [1][1]. Also [2] and [9].", HITS)
    assert [c.n for c in cits] == [1, 2]
    assert cits[0].chunk_id == 7 and cits[1].doc_id == "d1"


def test_answer_question_uses_provider_and_hits():
    class R:
        def search(self, q, top_k=5):
            return HITS[:top_k]

    p = FakeProvider(["Meals are forty dollars per day [1]."])
    a = answer_question("meals?", R(), p, top_k=2)
    assert isinstance(a, Answer)
    assert a.citations[0].chunk_id == 7 and len(a.hits) == 2
    assert p.calls[0][-1].role == "user"


def test_answer_question_with_no_hits_does_not_call_provider():
    class Empty:
        def search(self, q, top_k=5):
            return []

    p = FakeProvider([])
    a = answer_question("meals?", Empty(), p)
    assert a.citations == [] and p.calls == [] and "could not find" in a.text.lower()


def test_fake_provider_exhausted_raises():
    p = FakeProvider([])
    with pytest.raises(RuntimeError, match="exhausted"):
        p.generate([Message("user", "x")])


def test_fake_provider_callable_form():
    p = FakeProvider(lambda msgs: f"echo:{msgs[-1].content}")
    assert p.generate([Message("user", "hi")]) == "echo:hi"
