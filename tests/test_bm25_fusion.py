from docagent.index.bm25_index import BM25Index, tokenize
from docagent.retrieve.fusion import reciprocal_rank_fusion


def test_tokenize_lowercases_and_strips_punct():
    assert tokenize("Meals: $40/day!") == ["meals", "40", "day"]


def test_bm25_ranks_lexical_match_first(tmp_path):
    idx = BM25Index.build([
        (1, "meals are reimbursed up to forty dollars"),
        (2, "badge access to the office"),
        (3, "parental leave is twelve weeks"),
    ])
    assert idx.search("forty dollars meals", k=2)[0][0] == 1
    p = tmp_path / "bm25.pkl"
    idx.save(p)
    assert BM25Index.load(p).search("badge office", k=1)[0][0] == 2


def test_bm25_empty():
    assert BM25Index.build([]).search("x", k=3) == []
    assert len(BM25Index.build([])) == 0


def test_bm25_load_missing_file_is_empty(tmp_path):
    assert len(BM25Index.load(tmp_path / "missing.pkl")) == 0


def test_rrf_merges_rankings():
    fused = reciprocal_rank_fusion([[1, 2, 3], [3, 1, 4]], k=60)
    ids = [i for i, _ in fused]
    assert ids[0] == 1  # rank 1 and rank 2
    assert set(ids) == {1, 2, 3, 4}
    assert fused[0][1] > fused[-1][1]
