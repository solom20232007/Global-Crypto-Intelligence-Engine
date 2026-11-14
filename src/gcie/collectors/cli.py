"""Command-line entry point for public historical market-data backfills."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from gcie.collectors.public_market import (
    collect_binance_funding_rates,
    collect_binance_open_interest_snapshot,
    collect_binance_spot_klines,
    collect_bybit_funding_history,
    collect_bybit_open_interest_history,
    collect_okx_funding_history,
    collect_okx_history_candles,
    collect_okx_open_interest_snapshot,
)


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
        command.add_argument("--output", required=True, type=Path, help="Output JSONL path")
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
        ("okx-open-interest-snapshot", "Collect current OKX SWAP open interest"),
    ):
        command = subparsers.add_parser(name, help=help_text)
        command.add_argument(
            "--instrument", required=True, help="Native venue symbol/instrument ID"
        )
        command.add_argument("--output", required=True, type=Path, help="Output JSONL path")

    return parser


def collect(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.command == "binance-spot":
        return collect_binance_spot_klines(
            args.instrument, args.interval, args.start_ms, args.end_ms, limit=args.limit
        )
    if args.command == "binance-funding":
        return collect_binance_funding_rates(
            args.instrument, args.start_ms, args.end_ms, limit=args.limit
        )
    if args.command == "okx-candles":
        return collect_okx_history_candles(
            args.instrument, args.bar, args.start_ms, args.end_ms, limit=args.limit
        )
    if args.command == "okx-funding":
        return collect_okx_funding_history(
            args.instrument, args.start_ms, args.end_ms, limit=args.limit
        )
    if args.command == "bybit-funding":
        return collect_bybit_funding_history(
            args.category, args.instrument, args.start_ms, args.end_ms, limit=args.limit
        )
    if args.command == "bybit-open-interest":
        return collect_bybit_open_interest_history(
            args.category, args.instrument, args.interval, args.start_ms, args.end_ms,
            limit=args.limit,
        )
    if args.command == "binance-open-interest-snapshot":
        return [collect_binance_open_interest_snapshot(args.instrument)]
    if args.command == "okx-open-interest-snapshot":
        return [collect_okx_open_interest_snapshot(args.instrument)]
    raise ValueError(f"Unsupported command: {args.command}")


def main() -> int:
    args = build_parser().parse_args()
    rows = collect(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    summary = {
        "status": "ok",
        "command": args.command,
        "instrument": args.instrument,
        "rows_written": len(rows),
        "output": str(args.output),
    }
    if hasattr(args, "start_ms"):
        summary.update({"start_ms": args.start_ms, "end_ms_exclusive": args.end_ms})
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
