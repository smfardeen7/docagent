from dataclasses import dataclass

from docagent.index.bm25_index import BM25Index
from docagent.index.embedder import Embedder
from docagent.index.vector_index import VectorIndex
from docagent.retrieve.fusion import reciprocal_rank_fusion
from docagent.retrieve.reranker import Reranker
from docagent.store import Store


@dataclass(frozen=True)
class Hit:
    chunk_id: int
    doc_id: str
    ordinal: int
    text: str
    score: float


class Retriever:
    """Hybrid retrieval: dense top-k and BM25 top-k fused with RRF, then cross-encoder reranked."""

    def __init__(self, embedder: Embedder, vector_index: VectorIndex, bm25_index: BM25Index, reranker: Reranker,
                 store: Store, dense_k: int = 20, bm25_k: int = 20, rerank_k: int = 10):
        self.embedder = embedder
        self.vector_index = vector_index
        self.bm25_index = bm25_index
        self.reranker = reranker
        self.store = store
        self.dense_k = dense_k
        self.bm25_k = bm25_k
        self.rerank_k = rerank_k

    def search(self, query: str, top_k: int = 5) -> list[Hit]:
        dense = [i for i, _ in self.vector_index.search(self.embedder.encode_query(query), self.dense_k)]
        sparse = [i for i, _ in self.bm25_index.search(query, self.bm25_k)]
        fused = [i for i, _ in reciprocal_rank_fusion([dense, sparse])][: self.rerank_k]
        if not fused:
            return []
        chunks = self.store.get_chunks(fused)
        scores = self.reranker.score(query, [c["text"] for c in chunks])
        ranked = sorted(zip(chunks, scores), key=lambda cs: cs[1], reverse=True)[:top_k]
        return [Hit(c["id"], c["doc_id"], c["ordinal"], c["text"], float(s)) for c, s in ranked]
