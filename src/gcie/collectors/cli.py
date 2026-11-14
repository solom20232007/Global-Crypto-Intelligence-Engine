"""Command-line entry point for public historical market-data backfills.

Range commands split [start_ms, end_ms) into partitions. With --db, every partition
is committed to SQLite together with its raw provider pages and a checkpoint, so an
interrupted run can simply be re-run: partitions already marked complete are skipped.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from gcie.collectors.public_market import (
    JsonFetcher,
    collect_binance_funding_rates,
    collect_binance_open_interest_snapshot,
    collect_binance_spot_klines,
    collect_bybit_funding_history,
    collect_bybit_open_interest_history,
    collect_okx_funding_history,
    collect_okx_history_candles,
    collect_okx_open_interest_snapshot,
    public_json,
)
from gcie.storage.sqlite_store import SQLiteResearchStore

DAY_MS = 86_400_000

RangeCollector = Callable[
    [argparse.Namespace, int, int, JsonFetcher, int], list[dict[str, Any]]
]


@dataclass(frozen=True, slots=True)
class RangeCommand:
    venue: str
    stream: Callable[[argparse.Namespace], str]
    collect: RangeCollector
    default_chunk_ms: int


RANGE_COMMANDS: dict[str, RangeCommand] = {
    "binance-spot": RangeCommand(
        "binance",
        lambda a: f"ohlcv_{a.interval}",
        lambda a, s, e, f, now: collect_binance_spot_klines(
            a.instrument, a.interval, s, e, limit=a.limit, fetcher=f, now_ms=now
        ),
        DAY_MS,
    ),
    "binance-funding": RangeCommand(
        "binance",
        lambda a: "funding_rate",
        lambda a, s, e, f, _now: collect_binance_funding_rates(
            a.instrument, s, e, limit=a.limit, fetcher=f
        ),
        30 * DAY_MS,
    ),
    "okx-candles": RangeCommand(
        "okx",
        lambda a: f"ohlcv_{a.bar}",
        lambda a, s, e, f, _now: collect_okx_history_candles(
            a.instrument, a.bar, s, e, limit=a.limit, fetcher=f
        ),
        DAY_MS,
    ),
    "okx-funding": RangeCommand(
        "okx",
        lambda a: "funding_rate",
        lambda a, s, e, f, _now: collect_okx_funding_history(
            a.instrument, s, e, limit=a.limit, fetcher=f
        ),
        30 * DAY_MS,
    ),
    "bybit-funding": RangeCommand(
        "bybit",
        lambda a: f"funding_rate_{a.category}",
        lambda a, s, e, f, _now: collect_bybit_funding_history(
            a.category, a.instrument, s, e, limit=a.limit, fetcher=f
        ),
        30 * DAY_MS,
    ),
    "bybit-open-interest": RangeCommand(
        "bybit",
        lambda a: f"open_interest_{a.category}_{a.interval}",
        lambda a, s, e, f, _now: collect_bybit_open_interest_history(
            a.category, a.instrument, a.interval, s, e, limit=a.limit, fetcher=f
        ),
        7 * DAY_MS,
    ),
}

SNAPSHOT_COMMANDS: dict[str, Callable[[str, JsonFetcher], dict[str, Any]]] = {
    "binance-open-interest-snapshot": lambda i, f: collect_binance_open_interest_snapshot(
        i, fetcher=f
    ),
    "okx-open-interest-snapshot": lambda i, f: collect_okx_open_interest_snapshot(i, fetcher=f),
}


class RecordingFetcher:
    """Wrap a fetcher and keep every raw response so it can be persisted."""

    def __init__(self, fetcher: JsonFetcher) -> None:
        self._fetcher = fetcher
        self.pages: list[dict[str, Any]] = []

    def __call__(self, url: str) -> Any:
        payload = self._fetcher(url)
        self.pages.append({"url": url, "response": payload})
        return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    def common(name: str, help_text: str) -> argparse.ArgumentParser:
        command = subparsers.add_parser(name, help=help_text)
        command.add_argument(
            "--instrument", required=True, help="Native venue symbol/instrument ID"
        )
        command.add_argument(
            "--start-ms", required=True, type=int, help="Inclusive UTC epoch milliseconds"
        )
        command.add_argument(
            "--end-ms", required=True, type=int, help="Exclusive UTC epoch milliseconds"
        )
        command.add_argument(
            "--output", type=Path,
            help="JSONL path for rows fetched in this run (partitions skipped on resume "
                 "are not re-exported)",
        )
        command.add_argument(
            "--db", type=Path,
            help="SQLite path; enables per-partition commits and resume after interruption",
        )
        command.add_argument(
            "--chunk-ms", type=int, default=None,
            help="Partition size in milliseconds (default depends on the command)",
        )
        return command

    spot = common("binance-spot", "Backfill Binance spot OHLCV")
    spot.add_argument("--interval", default="1m")
    spot.add_argument("--limit", type=int, default=1000)

    funding = common("binance-funding", "Backfill Binance USDⓈ-M funding history")
    funding.add_argument("--limit", type=int, default=1000)

    okx_candles = common("okx-candles", "Backfill OKX historical candles")
    okx_candles.add_argument("--bar", default="1m")
    okx_candles.add_argument("--limit", type=int, default=100)

    okx_funding = common("okx-funding", "Backfill OKX perpetual funding history")
    okx_funding.add_argument("--limit", type=int, default=100)

    bybit_funding = common("bybit-funding", "Backfill Bybit linear/inverse funding history")
    bybit_funding.add_argument("--category", choices=("linear", "inverse"), default="linear")
    bybit_funding.add_argument("--limit", type=int, default=200)

    bybit_oi = common("bybit-open-interest", "Backfill Bybit historical open interest")
    bybit_oi.add_argument("--category", choices=("linear", "inverse"), default="linear")
    bybit_oi.add_argument(
        "--interval",
        choices=("5min", "15min", "30min", "1h", "4h", "1d"),
        default="1h",
    )
    bybit_oi.add_argument("--limit", type=int, default=200)

    for name, help_text in (
        ("binance-open-interest-snapshot", "Collect current Binance USDⓈ-M open interest"),
        ("okx-open-interest-snapshot", "Collect current OKX SWAP/FUTURES/OPTION open interest"),
    ):
        command = subparsers.add_parser(name, help=help_text)
        command.add_argument(
            "--instrument", required=True, help="Native venue symbol/instrument ID"
        )
        command.add_argument("--output", required=True, type=Path, help="Output JSONL path")

    return parser


def iter_partitions(start_ms: int, end_ms: int, chunk_ms: int) -> Iterator[tuple[int, int]]:
    """Yield [start, end) partitions aligned to a fixed epoch grid.

    Grid alignment keeps partition keys stable across runs with different ranges,
    so a wider re-run reuses checkpoints of the full partitions it overlaps.
    """
    if chunk_ms <= 0:
        raise ValueError("chunk_ms must be positive")
    if start_ms < 0 or end_ms <= start_ms:
        raise ValueError("Require 0 <= start_ms < end_ms")
    cursor = start_ms
    while cursor < end_ms:
        boundary = (cursor // chunk_ms + 1) * chunk_ms
        partition_end = min(boundary, end_ms)
        yield cursor, partition_end
        cursor = partition_end


def collect(args: argparse.Namespace, fetcher: JsonFetcher = public_json) -> list[dict[str, Any]]:
    """Collect a full command in memory (no persistence); kept for library callers."""
    if args.command in SNAPSHOT_COMMANDS:
        return [SNAPSHOT_COMMANDS[args.command](args.instrument, fetcher)]
    if args.command in RANGE_COMMANDS:
        return RANGE_COMMANDS[args.command].collect(
            args, args.start_ms, args.end_ms, fetcher, int(time.time() * 1000)
        )
    raise ValueError(f"Unsupported command: {args.command}")


def _write_rows(output: TextIO, rows: Sequence[dict[str, Any]]) -> None:
    for row in rows:
        output.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def run_range_command(
    args: argparse.Namespace,
    *,
    fetcher: JsonFetcher = public_json,
    now_ms: int | None = None,
    log: TextIO = sys.stderr,
) -> dict[str, Any]:
    spec = RANGE_COMMANDS[args.command]
    # Venue symbols are upper-case; collectors upper-case them, so keys must match.
    args.instrument = args.instrument.upper()
    stream = spec.stream(args)
    chunk_ms = args.chunk_ms or spec.default_chunk_ms
    now = int(time.time() * 1000) if now_ms is None else now_ms
    store = SQLiteResearchStore(args.db) if args.db else None

    stats = {"partitions": 0, "skipped": 0, "committed": 0, "partial": 0, "rows": 0}
    output = None
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        output = args.output.open("w", encoding="utf-8")
    try:
        for start, end in iter_partitions(args.start_ms, args.end_ms, chunk_ms):
            stats["partitions"] += 1
            key = {
                "venue": spec.venue, "metric": stream, "instrument": args.instrument,
                "partition_start_ms": start, "partition_end_ms": end,
            }
            if store is not None:
                checkpoint = store.get_checkpoint(**key)
                if checkpoint is not None and checkpoint["status"] == "complete":
                    stats["skipped"] += 1
                    continue

            recorder = RecordingFetcher(fetcher)
            rows = spec.collect(args, start, end, recorder, now)
            # A partition reaching into the future may still change (open candle,
            # upcoming funding), so it stays 'running' and is fetched again next run.
            complete = end <= now

            if store is not None:
                stored_rows = [{**row, "metric": stream} for row in rows]
                page_key = f"{spec.venue}:{stream}:{args.instrument}:{start}-{end}"
                if not complete:
                    page_key += f"@{now}"
                store.commit_page(
                    **key,
                    page_key=page_key,
                    raw_payload=recorder.pages,
                    observations=stored_rows,
                    next_cursor=str(end),
                    status="complete" if complete else "running",
                )
            if output is not None:
                _write_rows(output, rows)
                output.flush()

            stats["committed" if complete else "partial"] += 1
            stats["rows"] += len(rows)
            print(
                json.dumps({"partition": [start, end], "rows": len(rows),
                            "status": "complete" if complete else "running"}),
                file=log,
            )
    finally:
        if output is not None:
            output.close()
    return stats


def main(
    argv: Sequence[str] | None = None,
    *,
    fetcher: JsonFetcher = public_json,
    now_ms: int | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    summary: dict[str, Any] = {"command": args.command, "instrument": args.instrument}

    if args.command in SNAPSHOT_COMMANDS:
        rows = collect(args, fetcher)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8") as output:
            _write_rows(output, rows)
        summary.update({"rows_written": len(rows), "output": str(args.output)})
    else:
        if args.output is None and args.db is None:
            parser.error("at least one of --output or --db is required")
        if args.chunk_ms is not None and args.chunk_ms <= 0:
            parser.error("--chunk-ms must be positive")
        if args.start_ms < 0 or args.end_ms <= args.start_ms:
            parser.error("require 0 <= --start-ms < --end-ms")
        stats = run_range_command(args, fetcher=fetcher, now_ms=now_ms)
        summary.update({
            "instrument": args.instrument,
            "start_ms": args.start_ms,
            "end_ms_exclusive": args.end_ms,
            "partitions_total": stats["partitions"],
            "partitions_skipped": stats["skipped"],
            "partitions_committed": stats["committed"],
            "partitions_partial": stats["partial"],
            "rows_fetched": stats["rows"],
            "output": str(args.output) if args.output else None,
            "db": str(args.db) if args.db else None,
        })

    print(json.dumps({"status": "ok", **summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
