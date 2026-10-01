"""SQLite helper. The data directory and DB files are owner-only (0700 / 0600)."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path


def connect(path: Path | str) -> sqlite3.Connection:
    path = Path(path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(path.parent, 0o700)
        except OSError:
            pass
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    if str(path) != ":memory:":
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return conn
