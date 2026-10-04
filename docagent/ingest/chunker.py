from dataclasses import dataclass
from functools import lru_cache

from transformers import AutoTokenizer, PreTrainedTokenizerFast


@lru_cache
def get_tokenizer(model_name: str) -> PreTrainedTokenizerFast:
    return AutoTokenizer.from_pretrained(model_name)


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    text: str
    token_count: int


class Chunker:
    """Split text into token windows with overlap, measured by the embedding model's tokenizer."""

    def __init__(self, tokenizer: PreTrainedTokenizerFast, chunk_tokens: int = 256, overlap: int = 32):
        if overlap >= chunk_tokens:
            raise ValueError("overlap must be smaller than chunk_tokens")
        self.tokenizer = tokenizer
        self.chunk_tokens = chunk_tokens
        self.overlap = overlap

    def split(self, text: str) -> list[Chunk]:
        if not text.strip():
            return []
        enc = self.tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
        offsets = enc["offset_mapping"]
        n = len(offsets)
        if n == 0:
            return []
        stride = self.chunk_tokens - self.overlap
        chunks: list[Chunk] = []
        start = 0
        ordinal = 0
        while start < n:
            end = min(start + self.chunk_tokens, n)
            char_start = offsets[start][0]
            char_end = offsets[end - 1][1]
            piece = text[char_start:char_end].strip()
            if piece:
                chunks.append(Chunk(ordinal=ordinal, text=piece, token_count=end - start))
                ordinal += 1
            if end == n:
                break
            start += stride
        return chunks
