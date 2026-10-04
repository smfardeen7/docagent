import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "eval" / "corpus"
QUESTIONS = ROOT / "eval" / "questions.jsonl"

EXPECTED_DOCS = {
    "expense-policy", "travel-policy", "pto-and-leave", "security-policy",
    "onboarding", "remote-work", "equipment", "product-faq",
}


def load():
    docs = {p.stem: p.read_text().lower() for p in CORPUS.glob("*.md") if p.name != "README.md"}
    qs = [json.loads(line) for line in QUESTIONS.read_text().splitlines() if line.strip()]
    return docs, qs


def test_corpus_has_the_eight_documents_and_a_readme():
    docs, _ = load()
    assert set(docs) == EXPECTED_DOCS
    assert (CORPUS / "README.md").exists()
    for name, text in docs.items():
        assert 350 <= len(text.split()) <= 900, f"{name} has {len(text.split())} words"


def test_questions_reference_real_corpus_substrings():
    docs, qs = load()
    assert len(qs) >= 40 and len({q["id"] for q in qs}) == len(qs)
    for q in qs:
        assert set(q) >= {"id", "question", "gold_doc", "gold_substring", "answer_keywords", "kind"}, q.get("id")
        assert q["gold_doc"] in docs, q["id"]
        assert q["gold_substring"].lower() in docs[q["gold_doc"]], q["id"]
        assert q["kind"] in {"lookup", "multi", "calc"} and q["answer_keywords"], q["id"]
        assert all(isinstance(k, str) and k for k in q["answer_keywords"]), q["id"]


def test_question_kinds_are_mixed():
    _, qs = load()
    kinds = Counter(q["kind"] for q in qs)
    assert kinds["lookup"] >= 25 and kinds["multi"] >= 5 and kinds["calc"] >= 3
