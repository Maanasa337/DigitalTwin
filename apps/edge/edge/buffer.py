"""SQLite store-and-forward queue (FR-EDGE-03).

A prediction the broker cannot take right now is written here instead of being lost, and replayed
oldest-first on reconnect. The file survives a restart of the runner, so a power cut on the line
does not lose what was queued either.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import Callable
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    payload BLOB NOT NULL,
    qos INTEGER NOT NULL DEFAULT 1,
    queued_at REAL NOT NULL
)
"""


class StoreAndForward:
    def __init__(self, path: Path | str) -> None:
        path = Path(path)
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        # MQTT callbacks run on paho's network thread, the runner on the main one: one connection,
        # guarded by a lock, rather than a connection per thread.
        self._conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(SCHEMA)
        self._lock = threading.Lock()

    def enqueue(self, topic: str, payload: bytes, qos: int = 1) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO outbox (topic, payload, qos, queued_at) VALUES (?, ?, ?, ?)",
                (topic, payload, qos, time.time()),
            )

    def pending(self) -> int:
        with self._lock:
            return int(self._conn.execute("SELECT count(*) FROM outbox").fetchone()[0])

    def drain(self, publish: Callable[[str, bytes, int], bool], batch: int = 100) -> int:
        """Publish queued messages oldest-first; stops at the first failure. Returns how many went out.

        A row is deleted only after `publish` reports success, so a crash mid-drain re-sends at most
        the one message in flight (ingest is idempotent on the prediction id).
        """
        sent = 0
        while True:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT id, topic, payload, qos FROM outbox ORDER BY id LIMIT ?", (batch,)
                ).fetchall()
            if not rows:
                return sent
            for row_id, topic, payload, qos in rows:
                if not publish(topic, bytes(payload), qos):
                    return sent
                with self._lock:
                    self._conn.execute("DELETE FROM outbox WHERE id = ?", (row_id,))
                sent += 1

    def close(self) -> None:
        with self._lock:
            self._conn.close()
