from pathlib import Path

from pypdf import PdfReader

TEXT_SUFFIXES = {".md", ".markdown", ".txt"}


class UnsupportedFileType(ValueError):
    pass


class EmptyDocument(ValueError):
    pass


def load_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
    elif suffix in TEXT_SUFFIXES:
        text = path.read_text(encoding="utf-8", errors="replace")
    else:
        raise UnsupportedFileType(f"unsupported file type: {suffix or '(none)'}")
    if not text.strip():
        raise EmptyDocument("no text extracted")
    return text
