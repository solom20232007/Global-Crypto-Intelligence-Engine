import json
from urllib.parse import parse_qs, urlparse

import pytest

from gcie.collectors.cli import build_parser, iter_partitions, main
from gcie.storage.sqlite_store import SQLiteResearchStore


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

MINUTE = 60_000
HOUR = 60 * MINUTE


def fake_binance_klines(history_minutes, *, fail_after_calls=None):
    calls = []

    def fetch(url):
        calls.append(url)
        if fail_after_calls is not None and len(calls) > fail_after_calls:
            raise ConnectionError("network dropped")
        params = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        start, end = int(params["startTime"]), int(params["endTime"])
        return [
            [t, "1", "2", "0.5", "1.5", "10", t + 59_999, "15", 3, "4", "5", "0"]
            for t in (i * MINUTE for i in range(history_minutes))
            if start <= t <= end
        ][: int(params["limit"])]

    return fetch, calls


def test_partitions_are_aligned_to_a_stable_grid():
    assert list(iter_partitions(30, 250, 100)) == [(30, 100), (100, 200), (200, 250)]
    assert list(iter_partitions(0, 200, 100)) == [(0, 100), (100, 200)]


def test_cli_requires_output_or_db(tmp_path):
    with pytest.raises(SystemExit):
        main(["binance-spot", "--instrument", "ABCUSDT", "--start-ms", "0", "--end-ms", "10"])


def test_cli_commits_partitions_and_resumes_after_failure(tmp_path, capsys):
    db = tmp_path / "research.sqlite"
    argv = [
        "binance-spot", "--instrument", "ABCUSDT", "--start-ms", "0",
        "--end-ms", str(3 * HOUR), "--chunk-ms", str(HOUR), "--db", str(db),
    ]
    now = 10 * HOUR

    # First run dies during the second partition: the first one must survive.
    fetch, _ = fake_binance_klines(180, fail_after_calls=1)
    with pytest.raises(ConnectionError):
        main(argv, fetcher=fetch, now_ms=now)
    store = SQLiteResearchStore(db)
    assert store.counts() == {"raw_pages": 1, "observations": 60, "checkpoints": 1}

    # Re-run: the completed partition is skipped, the rest is fetched.
    fetch, calls = fake_binance_klines(180)
    capsys.readouterr()
    main(argv, fetcher=fetch, now_ms=now)
    summary = json.loads(capsys.readouterr().out)
    assert summary["partitions_skipped"] == 1
    assert summary["partitions_committed"] == 2
    assert store.counts() == {"raw_pages": 3, "observations": 180, "checkpoints": 3}
    assert f"startTime={HOUR}&" in calls[0]  # resumed at the first unfinished partition

    # A third run has nothing left to do.
    fetch, calls = fake_binance_klines(180)
    main(argv, fetcher=fetch, now_ms=now)
    assert calls == []


def test_partition_reaching_into_the_future_stays_running(tmp_path):
    db = tmp_path / "research.sqlite"
    argv = [
        "binance-spot", "--instrument", "ABCUSDT", "--start-ms", "0",
        "--end-ms", str(2 * HOUR), "--chunk-ms", str(HOUR), "--db", str(db),
    ]
    now = HOUR + 30 * MINUTE  # second partition is still open
    for _ in range(2):
        fetch, _calls = fake_binance_klines(90)
        main(argv, fetcher=fetch, now_ms=now)
    store = SQLiteResearchStore(db)
    first = store.get_checkpoint(
        venue="binance", metric="ohlcv_1m", instrument="ABCUSDT",
        partition_start_ms=0, partition_end_ms=HOUR,
    )
    second = store.get_checkpoint(
        venue="binance", metric="ohlcv_1m", instrument="ABCUSDT",
        partition_start_ms=HOUR, partition_end_ms=2 * HOUR,
    )
    assert first["status"] == "complete"
    assert second["status"] == "running"
    assert store.counts()["observations"] == 90


def test_different_intervals_do_not_overwrite_each_other(tmp_path):
    db = tmp_path / "research.sqlite"
    fetch, _ = fake_binance_klines(60)
    for interval in ("1m", "5m"):
        main([
            "binance-spot", "--instrument", "ABCUSDT", "--interval", interval,
            "--start-ms", "0", "--end-ms", str(HOUR), "--db", str(db),
        ], fetcher=fetch, now_ms=10 * HOUR)
    assert SQLiteResearchStore(db).counts()["observations"] == 120


def test_jsonl_output_still_works_without_db(tmp_path):
    out = tmp_path / "rows.jsonl"
    fetch, _ = fake_binance_klines(120)
    main([
        "binance-spot", "--instrument", "ABCUSDT", "--start-ms", "0",
        "--end-ms", str(2 * HOUR), "--chunk-ms", str(HOUR), "--output", str(out),
    ], fetcher=fetch, now_ms=10 * HOUR)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 120
    # Same schema as the --db export: the metric names the interval.
    assert json.loads(lines[0])["metric"] == "ohlcv_1m"


def test_lowercase_instrument_is_normalised(tmp_path):
    db = tmp_path / "research.sqlite"
    fetch, _ = fake_binance_klines(60)
    main([
        "binance-spot", "--instrument", "abcusdt", "--start-ms", "0",
        "--end-ms", str(HOUR), "--db", str(db),
    ], fetcher=fetch, now_ms=10 * HOUR)
    assert SQLiteResearchStore(db).counts()["observations"] == 60


def test_jsonl_export_from_db_includes_skipped_partitions_after_resume(tmp_path):
    db = tmp_path / "research.sqlite"
    out = tmp_path / "complete.jsonl"
    argv = [
        "binance-spot", "--instrument", "ABCUSDT", "--start-ms", "0",
        "--end-ms", str(3 * HOUR), "--chunk-ms", str(HOUR),
        "--db", str(db), "--output", str(out),
    ]
    now = 10 * HOUR

    # First partition commits, then the next request fails.
    fetch, _ = fake_binance_klines(180, fail_after_calls=1)
    with pytest.raises(ConnectionError):
        main(argv, fetcher=fetch, now_ms=now)
    assert not out.exists()

    # Resume skips the first partition, but export contains every stored row.
    fetch, _ = fake_binance_klines(180)
    main(argv, fetcher=fetch, now_ms=now)
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 180
    assert [row["event_time_ms"] for row in rows] == list(range(0, 180 * MINUTE, MINUTE))
    assert all(row["metric"] == "ohlcv_1m" for row in rows)

    # A fully skipped rerun must still produce the complete JSONL export.
    fetch, calls = fake_binance_klines(180)
    main(argv, fetcher=fetch, now_ms=now)
    assert calls == []
    rows_again = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert rows_again == rows


def test_jsonl_schema_is_identical_with_and_without_db(tmp_path):
    base = [
        "binance-spot", "--instrument", "ABCUSDT", "--start-ms", "0",
        "--end-ms", str(HOUR),
    ]
    fetch, _ = fake_binance_klines(60)
    main([*base, "--output", str(tmp_path / "plain.jsonl")], fetcher=fetch, now_ms=10 * HOUR)
    main([*base, "--output", str(tmp_path / "db.jsonl"), "--db", str(tmp_path / "x.sqlite")],
         fetcher=fetch, now_ms=10 * HOUR)
    plain = (tmp_path / "plain.jsonl").read_text(encoding="utf-8")
    exported = (tmp_path / "db.jsonl").read_text(encoding="utf-8")
    assert plain == exported


@pytest.mark.parametrize("with_db", [False, True])
def test_failed_run_keeps_previous_export_and_leaves_no_temp_file(tmp_path, with_db):
    out = tmp_path / "rows.jsonl"
    out.write_text("previous complete export\n", encoding="utf-8")
    argv = [
        "binance-spot", "--instrument", "ABCUSDT", "--start-ms", "0",
        "--end-ms", str(3 * HOUR), "--chunk-ms", str(HOUR), "--output", str(out),
    ]
    if with_db:
        argv += ["--db", str(tmp_path / "x.sqlite")]
    fetch, _ = fake_binance_klines(180, fail_after_calls=1)
    with pytest.raises(ConnectionError):
        main(argv, fetcher=fetch, now_ms=10 * HOUR)
    assert out.read_text(encoding="utf-8") == "previous complete export\n"
    assert sorted(p.name for p in tmp_path.iterdir() if p.suffix == ".tmp") == []


def test_export_from_db_streams_in_batches(tmp_path):
    db = tmp_path / "x.sqlite"
    fetch, _ = fake_binance_klines(180)
    main([
        "binance-spot", "--instrument", "ABCUSDT", "--start-ms", "0",
        "--end-ms", str(3 * HOUR), "--db", str(db),
    ], fetcher=fetch, now_ms=10 * HOUR)
    store = SQLiteResearchStore(db)
    stream = store.iter_observations(
        venue="binance", metric="ohlcv_1m", instrument="ABCUSDT",
        start_ms=0, end_ms=3 * HOUR, batch_size=7,
    )
    assert not isinstance(stream, list)
    times = [row["event_time_ms"] for row in stream]
    assert times == list(range(0, 180 * MINUTE, MINUTE))
    assert store.get_observations(
        venue="binance", metric="ohlcv_1m", instrument="ABCUSDT",
        start_ms=HOUR, end_ms=2 * HOUR,
    )[0]["event_time_ms"] == HOUR


def test_summary_reports_exported_rows(tmp_path, capsys):
    fetch, _ = fake_binance_klines(60)
    main([
        "binance-spot", "--instrument", "ABCUSDT", "--start-ms", "0", "--end-ms", str(HOUR),
        "--db", str(tmp_path / "x.sqlite"), "--output", str(tmp_path / "o.jsonl"),
    ], fetcher=fetch, now_ms=10 * HOUR)
    summary = json.loads(capsys.readouterr().out)
    assert summary["rows_exported"] == 60

