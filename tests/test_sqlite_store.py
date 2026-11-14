import pytest

from gcie.storage.sqlite_store import SQLiteResearchStore


def sample_row(timestamp=1000):
    return {
        "venue": "binance",
        "market_type": "spot",
        "instrument": "ABCUSDT",
        "metric": "ohlcv",
        "event_time_ms": timestamp,
        "close": "1.2300",
    }


def test_page_raw_rows_and_checkpoint_commit_together(tmp_path):
    store = SQLiteResearchStore(tmp_path / "research.sqlite")
    count = store.commit_page(
        page_key="binance:ABCUSDT:ohlcv:0",
        venue="binance",
        metric="ohlcv",
        instrument="ABCUSDT",
        raw_payload={"data": [["1000", "1.2300"]]},
        observations=[sample_row()],
        partition_start_ms=0,
        partition_end_ms=2000,
        next_cursor="2000",
        status="complete",
    )

    assert count == 1
    assert store.counts() == {
        "raw_pages": 1, "observations": 1, "checkpoints": 1,
    }
    checkpoint = store.get_checkpoint(
        venue="binance", metric="ohlcv", instrument="ABCUSDT",
        partition_start_ms=0, partition_end_ms=2000,
    )
    assert checkpoint["next_cursor"] == "2000"
    assert checkpoint["status"] == "complete"


def test_replaying_page_is_idempotent(tmp_path):
    store = SQLiteResearchStore(tmp_path / "research.sqlite")
    kwargs = {
        "page_key": "page-1",
        "venue": "binance",
        "metric": "ohlcv",
        "instrument": "ABCUSDT",
        "raw_payload": {"page": 1},
        "observations": [sample_row(), sample_row()],
        "partition_start_ms": 0,
        "partition_end_ms": 2000,
        "next_cursor": "2000",
    }
    store.commit_page(**kwargs)
    store.commit_page(**kwargs)
    assert store.counts() == {
        "raw_pages": 1, "observations": 1, "checkpoints": 1,
    }


def test_invalid_partition_is_rejected(tmp_path):
    store = SQLiteResearchStore(tmp_path / "research.sqlite")
    with pytest.raises(ValueError, match="partition_start_ms"):
        store.commit_page(
            page_key="bad", venue="binance", metric="ohlcv",
            instrument="ABCUSDT", raw_payload={}, observations=[],
            partition_start_ms=10, partition_end_ms=10,
        )

def test_reusing_page_key_with_different_raw_payload_fails(tmp_path):
    store = SQLiteResearchStore(tmp_path / "research.sqlite")
    args = {
        "page_key": "page-1",
        "venue": "binance",
        "metric": "ohlcv",
        "instrument": "ABCUSDT",
        "raw_payload": {"page": 1},
        "observations": [sample_row()],
        "partition_start_ms": 0,
        "partition_end_ms": 2000,
    }
    store.commit_page(**args)
    args["raw_payload"] = {"page": "different"}
    with pytest.raises(ValueError, match="different raw payload"):
        store.commit_page(**args)
    assert store.counts()["raw_pages"] == 1

