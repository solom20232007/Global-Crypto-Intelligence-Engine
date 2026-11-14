"""Transactional local SQLite persistence for collector pages and checkpoints.

Raw provider payloads, normalized observations, and progress checkpoints are committed
in one transaction so a checkpoint can never advance ahead of the data it represents.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Mapping


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS raw_pages (
    page_key TEXT PRIMARY KEY,
    venue TEXT NOT NULL,
    metric TEXT NOT NULL,
    instrument TEXT NOT NULL,
    request_start_ms INTEGER,
    request_end_ms INTEGER,
    request_cursor TEXT,
    next_cursor TEXT,
    response_json TEXT NOT NULL,
    received_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE TABLE IF NOT EXISTS observations (
    venue TEXT NOT NULL,
    market_type TEXT NOT NULL,
    instrument TEXT NOT NULL,
    metric TEXT NOT NULL,
    event_time_ms INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    source_page_key TEXT,
    PRIMARY KEY (venue, market_type, instrument, metric, event_time_ms),
    FOREIGN KEY (source_page_key) REFERENCES raw_pages(page_key)
);
CREATE TABLE IF NOT EXISTS checkpoints (
    venue TEXT NOT NULL,
    metric TEXT NOT NULL,
    instrument TEXT NOT NULL,
    partition_start_ms INTEGER NOT NULL,
    partition_end_ms INTEGER NOT NULL,
    next_cursor TEXT,
    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'complete', 'failed')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (venue, metric, instrument, partition_start_ms, partition_end_ms)
);
CREATE INDEX IF NOT EXISTS idx_observations_time
ON observations (venue, metric, instrument, event_time_ms);
"""


class SQLiteResearchStore:
    """Small local store; safe to reopen between bounded collector runs."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    def commit_page(
        self,
        *,
        page_key: str,
        venue: str,
        metric: str,
        instrument: str,
        raw_payload: Any,
        observations: Iterable[Mapping[str, Any]],
        partition_start_ms: int,
        partition_end_ms: int,
        request_cursor: str | None = None,
        next_cursor: str | None = None,
        status: str = "running",
    ) -> int:
        """Atomically persist raw page, deduplicated rows, and its checkpoint.

        Replaying the same page_key is idempotent. Observation identity is based on
        venue/market/instrument/metric/event timestamp; latest replayed payload wins.
        """
        if not page_key or not venue or not metric or not instrument:
            raise ValueError("page_key, venue, metric, and instrument are required")
        if partition_start_ms < 0 or partition_end_ms <= partition_start_ms:
            raise ValueError("Require 0 <= partition_start_ms < partition_end_ms")
        if status not in {"pending", "running", "complete", "failed"}:
            raise ValueError("Unsupported checkpoint status")

        rows = list(observations)
        raw_json = json.dumps(raw_payload, ensure_ascii=False, sort_keys=True)
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT response_json FROM raw_pages WHERE page_key=?",
                (page_key,),
            ).fetchone()
            if existing and existing[0] != raw_json:
                raise ValueError("page_key already exists with a different raw payload")
            connection.execute(
                """INSERT INTO raw_pages (
                    page_key, venue, metric, instrument, request_start_ms,
                    request_end_ms, request_cursor, next_cursor, response_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(page_key) DO NOTHING""",
                (
                    page_key, venue, metric, instrument, partition_start_ms,
                    partition_end_ms, request_cursor, next_cursor, raw_json,
                ),
            )
            for row in rows:
                event_time_ms = int(row["event_time_ms"])
                identity = (
                    str(row["venue"]), str(row["market_type"]),
                    str(row["instrument"]), str(row["metric"]), event_time_ms,
                )
                connection.execute(
                    """INSERT INTO observations (
                        venue, market_type, instrument, metric, event_time_ms,
                        payload_json, source_page_key
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(venue, market_type, instrument, metric, event_time_ms)
                    DO UPDATE SET payload_json=excluded.payload_json,
                                  source_page_key=excluded.source_page_key""",
                    (*identity, json.dumps(dict(row), ensure_ascii=False, sort_keys=True),
                     page_key),
                )
            connection.execute(
                """INSERT INTO checkpoints (
                    venue, metric, instrument, partition_start_ms, partition_end_ms,
                    next_cursor, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(venue, metric, instrument, partition_start_ms, partition_end_ms)
                DO UPDATE SET next_cursor=excluded.next_cursor,
                              status=excluded.status,
                              updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')""",
                (
                    venue, metric, instrument, partition_start_ms,
                    partition_end_ms, next_cursor, status,
                ),
            )
        return len(rows)

    def get_checkpoint(
        self, *, venue: str, metric: str, instrument: str,
        partition_start_ms: int, partition_end_ms: int,
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """SELECT * FROM checkpoints WHERE venue=? AND metric=?
                AND instrument=? AND partition_start_ms=? AND partition_end_ms=?""",
                (venue, metric, instrument, partition_start_ms, partition_end_ms),
            ).fetchone()
        return dict(row) if row else None

    def counts(self) -> dict[str, int]:
        with self._connect() as connection:
            return {
                table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in ("raw_pages", "observations", "checkpoints")
            }
