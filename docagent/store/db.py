import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from docagent.ingest.chunker import Chunk

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY, filename TEXT NOT NULL, status TEXT NOT NULL,
  reason TEXT, n_chunks INTEGER DEFAULT 0, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id TEXT NOT NULL REFERENCES documents(id),
  ordinal INTEGER NOT NULL, text TEXT NOT NULL, token_count INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS chunks_doc ON chunks(doc_id, ordinal);
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, mode TEXT NOT NULL, question TEXT NOT NULL, answer TEXT,
  citations TEXT, status TEXT NOT NULL, latency_ms REAL, fallback_used INTEGER DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS traces (
  run_id TEXT NOT NULL REFERENCES runs(id), n INTEGER NOT NULL, thought TEXT,
  tool TEXT, args TEXT, observation TEXT, PRIMARY KEY (run_id, n)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    """SQLite persistence for documents, chunks, runs and agent traces. WAL mode so the API and worker can share it."""

    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False, isolation_level=None, timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)

    # --- documents
    def create_document(self, doc_id: str, filename: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO documents (id, filename, status, created_at) VALUES (?,?,?,?)",
                (doc_id, filename, "queued", _now()),
            )

    def set_document_status(self, doc_id: str, status: str, reason: str | None = None, n_chunks: int | None = None) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE documents SET status=?, reason=COALESCE(?, reason), n_chunks=COALESCE(?, n_chunks) WHERE id=?",
                (status, reason, n_chunks, doc_id),
            )

    def get_document(self, doc_id: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        return dict(row) if row else None

    def list_documents(self) -> list[dict]:
        return [dict(r) for r in self._conn.execute("SELECT * FROM documents ORDER BY created_at")]

    # --- chunks
    def add_chunks(self, doc_id: str, chunks: list[Chunk]) -> list[int]:
        ids: list[int] = []
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                for c in chunks:
                    cur = self._conn.execute(
                        "INSERT INTO chunks (doc_id, ordinal, text, token_count) VALUES (?,?,?,?)",
                        (doc_id, c.ordinal, c.text, c.token_count),
                    )
                    ids.append(int(cur.lastrowid))
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        return ids

    def get_chunk(self, chunk_id: int) -> dict | None:
        row = self._conn.execute("SELECT * FROM chunks WHERE id=?", (chunk_id,)).fetchone()
        return dict(row) if row else None

    def get_chunks(self, ids: list[int]) -> list[dict]:
        if not ids:
            return []
        marks = ",".join("?" for _ in ids)
        rows = {r["id"]: dict(r) for r in self._conn.execute(f"SELECT * FROM chunks WHERE id IN ({marks})", ids)}
        return [rows[i] for i in ids if i in rows]

    def all_chunks(self, including: str | None = None) -> list[tuple[int, str]]:
        """Chunks of ready documents, plus those of `including` (a document still being indexed)."""
        rows = self._conn.execute(
            "SELECT c.id, c.text FROM chunks c JOIN documents d ON d.id=c.doc_id "
            "WHERE d.status='ready' OR c.doc_id=? ORDER BY c.id",
            (including,),
        )
        return [(r["id"], r["text"]) for r in rows]

    def delete_chunks(self, doc_id: str) -> int:
        with self._lock:
            return self._conn.execute("DELETE FROM chunks WHERE doc_id=?", (doc_id,)).rowcount

    def neighbors(self, chunk_id: int) -> list[dict]:
        c = self.get_chunk(chunk_id)
        if not c:
            return []
        rows = self._conn.execute(
            "SELECT * FROM chunks WHERE doc_id=? AND ordinal BETWEEN ? AND ? ORDER BY ordinal",
            (c["doc_id"], c["ordinal"] - 1, c["ordinal"] + 1),
        )
        return [dict(r) for r in rows]

    def count_ready_chunks(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM chunks c JOIN documents d ON d.id=c.doc_id WHERE d.status='ready'"
        ).fetchone()
        return int(row[0])

    # --- runs
    def create_run(self, run_id: str, mode: str, question: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO runs (id, mode, question, status, created_at) VALUES (?,?,?,?,?)",
                (run_id, mode, question, "running", _now()),
            )

    def finish_run(self, run_id: str, answer: str | None, citations: list[dict], status: str, latency_ms: float,
                   fallback_used: bool = False) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE runs SET answer=?, citations=?, status=?, latency_ms=?, fallback_used=? WHERE id=?",
                (answer, json.dumps(citations), status, latency_ms, int(fallback_used), run_id),
            )

    def add_trace_step(self, run_id: str, step: dict) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO traces (run_id, n, thought, tool, args, observation) VALUES (?,?,?,?,?,?)",
                (run_id, step["n"], step.get("thought"), step.get("tool"), json.dumps(step.get("args", {})),
                 step.get("observation")),
            )

    def get_run(self, run_id: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            return None
        run = dict(row)
        run["citations"] = json.loads(run["citations"]) if run["citations"] else []
        run["fallback_used"] = bool(run["fallback_used"])
        run["steps"] = [
            {**dict(r), "args": json.loads(r["args"] or "{}")}
            for r in self._conn.execute(
                "SELECT n, thought, tool, args, observation FROM traces WHERE run_id=? ORDER BY n", (run_id,)
            )
        ]
        return run

    def close(self) -> None:
        self._conn.close()
