"""DocAgent: agentic RAG assistant over your own documents."""

import sys

__version__ = "0.1.0"

# On Linux, faiss-cpu and torch each ship their own OpenMP runtime. Loading faiss *after* torch has started
# threads can deadlock on the first faiss call (observed once in a worker container; the api in the same CI run
# was fine). Importing faiss first, before anything in this package pulls in torch, makes the init order fixed.
if sys.platform.startswith("linux"):
    try:
        import faiss  # noqa: F401
    except ImportError:
        pass
