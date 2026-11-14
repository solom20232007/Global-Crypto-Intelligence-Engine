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
