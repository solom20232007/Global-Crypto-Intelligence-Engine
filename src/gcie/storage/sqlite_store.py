"""Transactional local SQLite persistence for collector pages and checkpoints.

Raw provider payloads, normalized observations, and progress checkpoints are committed
in one transaction so a checkpoint can never advance ahead of the data it represents.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

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


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=_json_default)


class SQLiteResearchStore:
    """Small local store; safe to reopen between bounded collector runs."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        """Open a connection, run one explicit transaction, and always close it."""
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            try:
                yield connection
            except BaseException:
                connection.execute("ROLLBACK")
                raise
            connection.execute("COMMIT")
        finally:
            connection.close()

    def _initialize(self) -> None:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(SCHEMA)
        finally:
            connection.close()

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

        rows = [dict(row) for row in observations]
        raw_json = _dumps(raw_payload)
        prepared = []
        for row in rows:
            # venue/metric/instrument default to the page's values; a mismatch is a bug.
            page_identity = (("venue", venue), ("metric", metric), ("instrument", instrument))
            for key, page_value in page_identity:
                row.setdefault(key, page_value)
                if str(row[key]) != page_value:
                    raise ValueError(
                        f"Observation {key}={row[key]!r} does not match "
                        f"page {key}={page_value!r}"
                    )
            if "market_type" not in row or "event_time_ms" not in row:
                raise ValueError("Each observation needs market_type and event_time_ms")
            identity = (
                venue, str(row["market_type"]), instrument, metric, int(row["event_time_ms"]),
            )
            prepared.append((*identity, _dumps(row), page_key))

        with self._connect(write=True) as connection:
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
            connection.executemany(
                """INSERT INTO observations (
                    venue, market_type, instrument, metric, event_time_ms,
                    payload_json, source_page_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(venue, market_type, instrument, metric, event_time_ms)
                DO UPDATE SET payload_json=excluded.payload_json,
                              source_page_key=excluded.source_page_key""",
                prepared,
            )
            connection.execute(
                """INSERT INTO checkpoints (
                    venue, metric, instrument, partition_start_ms, partition_end_ms,
                    next_cursor, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(venue, metric, instrument, partition_start_ms, partition_end_ms)
                DO UPDATE SET next_cursor=excluded.next_cursor,
                              status=excluded.status,
                              updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE checkpoints.status != 'complete' OR excluded.status = 'complete'""",
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

    def iter_observations(
        self, *, venue: str, metric: str, instrument: str, start_ms: int, end_ms: int,
        batch_size: int = 5_000,
    ) -> Iterator[dict[str, Any]]:
        """Stream observations for one instrument in [start_ms, end_ms), oldest first.

        Rows are fetched in batches inside one read transaction, so memory use stays
        flat for multi-month 1-minute ranges and the result is a consistent snapshot.
        """
        if start_ms < 0 or end_ms <= start_ms:
            raise ValueError("Require 0 <= start_ms < end_ms")
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        with self._connect() as connection:
            cursor = connection.execute(
                """SELECT payload_json FROM observations
                WHERE venue=? AND metric=? AND instrument=?
                  AND event_time_ms >= ? AND event_time_ms < ?
                ORDER BY event_time_ms, market_type""",
                (venue, metric, instrument, start_ms, end_ms),
            )
            while batch := cursor.fetchmany(batch_size):
                for (payload_json,) in batch:
                    yield json.loads(payload_json)

    def get_observations(
        self, *, venue: str, metric: str, instrument: str, start_ms: int, end_ms: int
    ) -> list[dict[str, Any]]:
        """Return observations for one instrument in the half-open time range."""
        return list(self.iter_observations(
            venue=venue, metric=metric, instrument=instrument,
            start_ms=start_ms, end_ms=end_ms,
        ))

    def counts(self) -> dict[str, int]:
        with self._connect() as connection:
            return {
                table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in ("raw_pages", "observations", "checkpoints")
            }
