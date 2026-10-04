from docagent.eval.metrics import citation_precision, keyword_hit, percentile, recall_at_k, reciprocal_rank


def test_recall_and_rr():
    ranked = ["nothing", "limit is forty dollars", "x"]
    assert recall_at_k(ranked, "forty dollars", 1) == 0.0
    assert recall_at_k(ranked, "forty dollars", 3) == 1.0
    assert reciprocal_rank(ranked, "forty dollars") == 0.5
    assert reciprocal_rank(ranked, "absent") == 0.0


def test_keyword_hit_case_insensitive():
    assert keyword_hit("The limit is $40 per Day.", ["40", "day"]) is True
    assert keyword_hit("no", ["40"]) is False


def test_citation_precision():
    assert citation_precision(["forty dollars here", "unrelated"], "forty dollars") == 0.5
    assert citation_precision([], "x") is None


def test_percentile():
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert percentile([5], 95) == 5
    assert percentile([], 50) == 0.0
