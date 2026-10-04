def _contains(text: str, needle: str) -> bool:
    return needle.lower() in text.lower()


def recall_at_k(ranked_texts: list[str], gold_substring: str, k: int) -> float:
    return 1.0 if any(_contains(t, gold_substring) for t in ranked_texts[:k]) else 0.0


def reciprocal_rank(ranked_texts: list[str], gold_substring: str) -> float:
    for i, t in enumerate(ranked_texts, start=1):
        if _contains(t, gold_substring):
            return 1.0 / i
    return 0.0


def keyword_hit(answer: str, keywords: list[str]) -> bool:
    return all(_contains(answer, k) for k in keywords)


def citation_precision(cited_texts: list[str], gold_substring: str) -> float | None:
    if not cited_texts:
        return None
    return sum(_contains(t, gold_substring) for t in cited_texts) / len(cited_texts)


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    xs = sorted(values)
    pos = (len(xs) - 1) * p / 100
    lo, hi = int(pos), min(int(pos) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)
