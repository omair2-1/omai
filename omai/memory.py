"""Long-term memory (spec Phase 1).

Backed by SQLite + FTS5 keyword search (BM25 ranking). It has zero heavy dependencies and works
offline. The public interface (add / search / recent / delete) is deliberately small so a vector
backend (Chroma, Pinecone, ...) can be swapped in later without touching the agent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .db import connect

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    text, content='memories', content_rowid='id'
);
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
"""

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are", "was", "were",
    "be", "me", "my", "i", "you", "your", "it", "this", "that", "with", "at", "by", "as",
    "do", "does", "did", "what", "when", "where", "who", "how", "can", "could", "please",
}


@dataclass(frozen=True)
class Memory:
    id: int
    text: str
    created_at: str


def _fts_query(text: str) -> str | None:
    tokens = [t for t in re.findall(r"\w+", text.lower()) if len(t) > 1 and t not in _STOPWORDS]
    if not tokens:
        return None
    # Quote each token (neutralises FTS operators) and allow prefix matches.
    return " OR ".join(f'"{t}"*' for t in dict.fromkeys(tokens))


class MemoryStore:
    def __init__(self, path: Path | str):
        self._conn = connect(path)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def add(self, text: str) -> int:
        text = " ".join(text.split())
        if not text:
            raise ValueError("Cannot store an empty memory.")
        existing = self._conn.execute(
            "SELECT id FROM memories WHERE lower(text) = lower(?)", (text,)
        ).fetchone()
        if existing:
            return existing["id"]
        cur = self._conn.execute(
            "INSERT INTO memories (text, created_at) VALUES (?, ?)",
            (text, datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        self._conn.commit()
        return cur.lastrowid

    def get(self, memory_id: int) -> Memory | None:
        row = self._conn.execute(
            "SELECT id, text, created_at FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        return Memory(**dict(row)) if row else None

    def search(self, query: str, limit: int = 5) -> list[Memory]:
        q = _fts_query(query)
        if q is None:
            return []
        rows = self._conn.execute(
            """
            SELECT m.id, m.text, m.created_at
            FROM memories_fts f JOIN memories m ON m.id = f.rowid
            WHERE memories_fts MATCH ?
            ORDER BY bm25(memories_fts)
            LIMIT ?
            """,
            (q, limit),
        ).fetchall()
        return [Memory(**dict(r)) for r in rows]

    def recent(self, limit: int = 10) -> list[Memory]:
        rows = self._conn.execute(
            "SELECT id, text, created_at FROM memories ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [Memory(**dict(r)) for r in rows]

    def delete(self, memory_id: int) -> bool:
        cur = self._conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) AS n FROM memories").fetchone()["n"]
