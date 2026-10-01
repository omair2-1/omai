"""Append-only audit log of every tool call and every permission decision (spec Phase 11)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .db import connect

_SCHEMA = """
CREATE TABLE IF NOT EXISTS action_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,      -- tool_call | permission
    name TEXT NOT NULL,      -- tool name
    details TEXT NOT NULL,   -- JSON
    outcome TEXT NOT NULL    -- ok | error | allowed | denied | auto-allowed
);
"""

# Truncate large values so the log stays readable and never balloons with page/email bodies.
_MAX_VALUE_CHARS = 500


def _shrink(obj):
    if isinstance(obj, str):
        return obj if len(obj) <= _MAX_VALUE_CHARS else obj[:_MAX_VALUE_CHARS] + "…"
    if isinstance(obj, dict):
        return {k: _shrink(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_shrink(v) for v in obj]
    return obj


class AuditLog:
    def __init__(self, path: Path | str):
        self._conn = connect(path)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def log(self, kind: str, name: str, details: dict, outcome: str) -> None:
        self._conn.execute(
            "INSERT INTO action_log (ts, kind, name, details, outcome) VALUES (?,?,?,?,?)",
            (
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                kind,
                name,
                json.dumps(_shrink(details), ensure_ascii=False, default=str),
                outcome,
            ),
        )
        self._conn.commit()

    def recent(self, limit: int = 20) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, ts, kind, name, details, outcome FROM action_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
