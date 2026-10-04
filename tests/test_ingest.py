from pathlib import Path

import pytest

from docagent.ingest.chunker import Chunker
from docagent.ingest.loaders import EmptyDocument, UnsupportedFileType, load_text

FIX = Path(__file__).parent / "fixtures"


def test_load_markdown():
    assert "Expense policy" in load_text(FIX / "sample.md")


def test_unsupported_type(tmp_path):
    p = tmp_path / "x.docx"
    p.write_bytes(b"zz")
    with pytest.raises(UnsupportedFileType):
        load_text(p)


def test_empty_pdf_raises(tmp_path):
    from pypdf import PdfWriter

    p = tmp_path / "blank.pdf"
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    w.write(p)
    with pytest.raises(EmptyDocument):
        load_text(p)


def test_chunks_cover_text_and_respect_budget(tokenizer):
    text = " ".join(f"word{i}" for i in range(2000))
    chunks = Chunker(tokenizer, chunk_tokens=64, overlap=8).split(text)
    assert len(chunks) > 10
    assert all(c.token_count <= 64 for c in chunks)
    assert chunks[0].text.startswith("word0")
    assert chunks[-1].text.rstrip().endswith("word1999")
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))
    # overlap: the tail of chunk i reappears at the start of chunk i+1
    tail = chunks[0].text.split()[-3:]
    assert all(t in chunks[1].text for t in tail)


def test_short_text_single_chunk(tokenizer):
    chunks = Chunker(tokenizer, 256, 32).split("Just one sentence.")
    assert len(chunks) == 1 and chunks[0].ordinal == 0


def test_blank_text_no_chunks(tokenizer):
    assert Chunker(tokenizer, 256, 32).split("   \n ") == []
