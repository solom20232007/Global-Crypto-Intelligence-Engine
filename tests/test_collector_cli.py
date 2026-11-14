from gcie.collectors.cli import build_parser


def test_cli_requires_explicit_time_range_and_output():
    parser = build_parser()
    args = parser.parse_args([
        "binance-spot", "--instrument", "ABCUSDT",
        "--start-ms", "1000", "--end-ms", "2000",
        "--output", "tmp/abc.jsonl",
    ])
    assert args.command == "binance-spot"
    assert args.interval == "1m"
    assert args.start_ms == 1000
    assert args.end_ms == 2000


def test_cli_parses_bybit_derivatives_and_snapshot_commands():
    parser = build_parser()
    funding = parser.parse_args([
        "bybit-funding", "--instrument", "ABCUSDT", "--category", "linear",
        "--start-ms", "1000", "--end-ms", "2000", "--output", "tmp/funding.jsonl",
    ])
    open_interest = parser.parse_args([
        "bybit-open-interest", "--instrument", "ABCUSDT", "--category", "inverse",
        "--interval", "4h", "--start-ms", "1000", "--end-ms", "2000",
        "--output", "tmp/oi.jsonl",
    ])
    snapshot = parser.parse_args([
        "okx-open-interest-snapshot", "--instrument", "ABC-USDT-SWAP",
        "--output", "tmp/okx-oi.jsonl",
    ])
    assert funding.category == "linear"
    assert open_interest.interval == "4h"
    assert snapshot.command == "okx-open-interest-snapshot"
