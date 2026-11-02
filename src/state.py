"""Stato persistente: quali avvisi sono già stati processati (SQLite)."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_notices (
    pub_id     TEXT PRIMARY KEY,
    evt_code   TEXT NOT NULL,
    cnt_id     TEXT,
    title      TEXT,
    processed_at TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'ok'
);
"""


class StateStore:
    def __init__(self, db_path: Path = DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    # ── API ──────────────────────────────────────────────────────────────
    def is_processed(self, pub_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM processed_notices WHERE pub_id = ?", (str(pub_id),)
        ).fetchone()
        return row is not None

    def mark_processed(
        self,
        pub_id: str,
        evt_code: str,
        cnt_id: str | None = None,
        title: str | None = None,
        status: str = "ok",
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO processed_notices (pub_id, evt_code, cnt_id, title, processed_at, status)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(pub_id) DO UPDATE SET
                status = excluded.status,
                processed_at = excluded.processed_at
            """,
            (
                str(pub_id),
                evt_code,
                cnt_id,
                title,
                datetime.now(timezone.utc).isoformat(),
                status,
            ),
        )
        self._conn.commit()

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS n FROM processed_notices").fetchone()
        return int(row["n"])

    def close(self) -> None:
        self._conn.close()

    # ── Context manager ──────────────────────────────────────────────────
    def __enter__(self) -> "StateStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()