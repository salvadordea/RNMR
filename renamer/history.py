"""Persistent rename history backed by SQLite.

The database lives in the platform app-data directory alongside
settings.json.  It survives app restarts and is independent of the
folder being scanned.
"""
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# App-data directory (same logic as gui/settings.py)
# ---------------------------------------------------------------------------

def _app_data_dir() -> Path:
    import os
    import sys
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / "RNMR"
    d.mkdir(parents=True, exist_ok=True)
    return d


DB_PATH = _app_data_dir() / "rename_history.db"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class RenameEntry:
    """One file in a rename transaction."""
    old_path: str
    new_path: str


@dataclass
class RenameTransaction:
    """A batch rename operation that can be undone."""
    batch_id: str
    timestamp: str
    folder: str
    metadata_source: str
    items: list[RenameEntry] = field(default_factory=list)
    reverted: bool = False
    reverted_at: str | None = None


# ---------------------------------------------------------------------------
# RenameHistoryManager
# ---------------------------------------------------------------------------

class RenameHistoryManager:
    """SQLite-backed persistent rename history.

    Usage::

        mgr = RenameHistoryManager()
        mgr.save_transaction(folder, items, metadata_source)
        tx = mgr.get_last_undoable()
        mgr.mark_reverted(tx.batch_id)
    """

    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path or DB_PATH
        self._conn: sqlite3.Connection | None = None
        self._ensure_schema()

    # -- connection management -------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,
            )
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def _ensure_schema(self) -> None:
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS transactions (
                batch_id        TEXT PRIMARY KEY,
                timestamp       TEXT NOT NULL,
                folder          TEXT NOT NULL,
                metadata_source TEXT NOT NULL DEFAULT 'inferred',
                reverted        INTEGER NOT NULL DEFAULT 0,
                reverted_at     TEXT
            );

            CREATE TABLE IF NOT EXISTS rename_items (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id    TEXT NOT NULL,
                old_path    TEXT NOT NULL,
                new_path    TEXT NOT NULL,
                FOREIGN KEY (batch_id) REFERENCES transactions(batch_id)
            );

            CREATE INDEX IF NOT EXISTS idx_items_batch
                ON rename_items(batch_id);
        """)
        conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # -- public API ------------------------------------------------

    def save_transaction(
        self,
        folder: str,
        items: list[dict[str, Any]],
        metadata_source: str = "inferred",
    ) -> str:
        """Persist a rename transaction.

        *items* is a list of dicts, each with keys ``old_path`` and
        ``new_path`` (absolute path strings).

        Returns the generated ``batch_id``.
        """
        batch_id = uuid.uuid4().hex[:12]
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

        conn = self._get_conn()
        conn.execute(
            "INSERT INTO transactions (batch_id, timestamp, folder, metadata_source) "
            "VALUES (?, ?, ?, ?)",
            (batch_id, timestamp, folder, metadata_source),
        )
        conn.executemany(
            "INSERT INTO rename_items (batch_id, old_path, new_path) "
            "VALUES (?, ?, ?)",
            [
                (batch_id, item["old_path"], item["new_path"])
                for item in items
            ],
        )
        conn.commit()
        return batch_id

    def has_undoable(self) -> bool:
        """Return True if at least one non-reverted transaction exists."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT 1 FROM transactions WHERE reverted = 0 LIMIT 1"
        ).fetchone()
        return row is not None

    def get_last_undoable(self) -> RenameTransaction | None:
        """Return the most recent non-reverted transaction, or None."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT batch_id, timestamp, folder, metadata_source "
            "FROM transactions "
            "WHERE reverted = 0 "
            "ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None

        batch_id, timestamp, folder, metadata_source = row

        item_rows = conn.execute(
            "SELECT old_path, new_path FROM rename_items "
            "WHERE batch_id = ? ORDER BY id",
            (batch_id,),
        ).fetchall()

        tx = RenameTransaction(
            batch_id=batch_id,
            timestamp=timestamp,
            folder=folder,
            metadata_source=metadata_source,
            items=[
                RenameEntry(old_path=r[0], new_path=r[1])
                for r in item_rows
            ],
        )
        return tx

    def mark_reverted(self, batch_id: str) -> None:
        """Mark a transaction as reverted."""
        reverted_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        conn = self._get_conn()
        conn.execute(
            "UPDATE transactions SET reverted = 1, reverted_at = ? "
            "WHERE batch_id = ?",
            (reverted_at, batch_id),
        )
        conn.commit()

    def get_all_transactions(
        self, limit: int = 50
    ) -> list[RenameTransaction]:
        """Return recent transactions (newest first), for a future history dialog."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT batch_id, timestamp, folder, metadata_source, reverted, reverted_at "
            "FROM transactions ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()

        transactions = []
        for batch_id, timestamp, folder, metadata_source, reverted, reverted_at in rows:
            item_rows = conn.execute(
                "SELECT old_path, new_path FROM rename_items "
                "WHERE batch_id = ? ORDER BY id",
                (batch_id,),
            ).fetchall()
            transactions.append(RenameTransaction(
                batch_id=batch_id,
                timestamp=timestamp,
                folder=folder,
                metadata_source=metadata_source,
                items=[
                    RenameEntry(old_path=r[0], new_path=r[1])
                    for r in item_rows
                ],
                reverted=bool(reverted),
                reverted_at=reverted_at,
            ))
        return transactions
