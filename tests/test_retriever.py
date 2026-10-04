from docagent.index import BM25Index, HashEmbedder, VectorIndex
from docagent.ingest.chunker import Chunk
from docagent.retrieve import Hit, LexicalReranker, Retriever
from docagent.store import Store

TEXTS = [
    "Meals are reimbursed up to forty dollars per day while travelling.",
    "Badge access to the office requires a photo ID.",
    "Parental leave is twelve weeks at full pay.",
    "Laptops must be encrypted with FileVault.",
]


def build(tmp_path):
    store = Store(tmp_path / "t.db")
    store.create_document("d1", "handbook.md")
    ids = store.add_chunks("d1", [Chunk(i, t, 10) for i, t in enumerate(TEXTS)])
    store.set_document_status("d1", "ready", n_chunks=len(ids))
    emb = HashEmbedder(32)
    vi = VectorIndex(32, backend="numpy")
    vi.add(ids, emb.encode(TEXTS))
    bm = BM25Index.build(list(zip(ids, TEXTS)))
    return Retriever(emb, vi, bm, LexicalReranker(), store, dense_k=4, bm25_k=4, rerank_k=4)


def test_hybrid_search_returns_hits_with_metadata(tmp_path):
    r = build(tmp_path)
    hits = r.search("how much for meals per day", top_k=2)
    assert len(hits) == 2 and isinstance(hits[0], Hit)
    assert "forty dollars" in hits[0].text
    assert hits[0].doc_id == "d1" and hits[0].ordinal == 0
    assert hits[0].score >= hits[1].score


def test_lexical_reranker_scores_overlap():
    s = LexicalReranker().score("badge office", ["badge access office", "parental leave"])
    assert s[0] > s[1]


def test_search_empty_indexes(tmp_path):
    store = Store(tmp_path / "t.db")
    r = Retriever(HashEmbedder(8), VectorIndex(8, backend="numpy"), BM25Index.build([]), LexicalReranker(), store)
    assert r.search("anything", top_k=3) == []
