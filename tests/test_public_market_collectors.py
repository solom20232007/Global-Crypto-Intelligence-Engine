from urllib.parse import parse_qs, urlparse

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


def _query(url):
    return {key: values[0] for key, values in parse_qs(urlparse(url).query).items()}


def binance_like(history, time_key):
    """Fake Binance endpoint honouring startTime/endTime (inclusive) and limit."""
    def fetch(url):
        params = _query(url)
        start, end = int(params["startTime"]), int(params["endTime"])
        rows = sorted(
            (r for r in history if start <= int(r[time_key]) <= end),
            key=lambda r: int(r[time_key]),
        )
        return rows[: int(params["limit"])]
    return fetch


def okx_like(history, time_key, *, server_max_limit=100):
    """Fake OKX endpoint: newest-first rows strictly older than 'after', capped limit."""
    def fetch(url):
        params = _query(url)
        after = int(params["after"])
        limit = min(int(params.get("limit", 100)), server_max_limit)
        rows = sorted(
            (r for r in history if int(r[time_key]) < after),
            key=lambda r: int(r[time_key]), reverse=True,
        )
        return {"code": "0", "data": rows[:limit]}
    return fetch


def test_binance_klines_are_normalized_and_sorted():
    payload = [
        [60_000, "1", "2", "0.5", "1.5", "10", 119_999, "15", 7, "6", "9", "0"],
        [0, "1", "2", "0.5", "1.2", "8", 59_999, "10", 5, "4", "5", "0"],
    ]
    rows = collect_binance_spot_klines(
        "abcusdt", "1m", 0, 120_000, limit=2,
        fetcher=lambda _url: payload, pause_seconds=0,
    )
    assert [row["event_time_ms"] for row in rows] == [0, 60_000]
    assert rows[0]["taker_buy_base"] == "4"
    assert rows[1]["venue"] == "binance"


def test_binance_funding_keeps_rates_as_decimal_strings():
    rows = collect_binance_funding_rates(
        "ABCUSDT", 0, 2000,
        fetcher=binance_like([{"fundingTime": 1000, "fundingRate": "0.000125"}], "fundingTime"),
        pause_seconds=0,
    )
    assert rows[0]["funding_rate"] == "0.000125"
    assert rows[0]["market_type"] == "perpetual"


def test_okx_candles_normalize_quote_volume_and_confirmation():
    payload = {"code": "0", "data": [
        ["1000", "1", "2", "0.5", "1.5", "10", "10", "15", "1"]
    ]}
    rows = collect_okx_history_candles(
        "ABC-USDT", "1m", 0, 2000, fetcher=okx_like(payload["data"], 0), pause_seconds=0,
    )
    assert rows[0]["volume_quote"] == "15"
    assert rows[0]["confirmed"] is True


def test_okx_funding_history_is_normalized():
    payload = {"code": "0", "data": [
        {"fundingTime": "1000", "fundingRate": "0.0001"}
    ]}
    rows = collect_okx_funding_history(
        "ABC-USDT-SWAP", 0, 2000, fetcher=okx_like(payload["data"], "fundingTime"),
        pause_seconds=0,
    )
    assert rows[0]["funding_rate"] == "0.0001"
    assert rows[0]["venue"] == "okx"


def test_invalid_ranges_are_rejected():
    try:
        collect_binance_spot_klines("ABCUSDT", "1m", 10, 10)
    except ValueError as exc:
        assert "start_ms" in str(exc)
    else:
        raise AssertionError("Invalid time range must fail")




def test_bybit_funding_paginates_backwards_and_preserves_decimal_strings():
    calls = []

    def fetch(url):
        params = parse_qs(urlparse(url).query)
        calls.append(params)
        history = [
            {"fundingRateTimestamp": "3000", "fundingRate": "0.00012300"},
            {"fundingRateTimestamp": "2000", "fundingRate": "-0.00004000"},
            {"fundingRateTimestamp": "1000", "fundingRate": "0.00001000"},
        ]
        start, end = int(params["startTime"][0]), int(params["endTime"][0])
        limit = int(params["limit"][0])
        rows = [r for r in history if start <= int(r["fundingRateTimestamp"]) <= end][:limit]
        return {"retCode": 0, "result": {"list": rows}}

    rows = collect_bybit_funding_history(
        "linear", "ABCUSDT", 0, 4000, limit=2, fetcher=fetch, pause_seconds=0,
    )
    assert [row["event_time_ms"] for row in rows] == [1000, 2000, 3000]
    assert rows[2]["funding_rate"] == "0.00012300"
    assert calls[1]["endTime"] == ["1999"]


def test_bybit_open_interest_uses_cursor_and_orders_timestamps():
    calls = []

    def fetch(url):
        params = parse_qs(urlparse(url).query)
        calls.append(params)
        if len(calls) == 1:
            return {
                "retCode": 0,
                "result": {
                    "list": [
                        {
                            "timestamp": "2000",
                            "openInterest": "123.4500",
                            "singleOpenInterest": "61.7250",
                        }
                    ],
                    "nextPageCursor": "cursor-2",
                },
            }
        return {
            "retCode": 0,
            "result": {
                "list": [{
                    "timestamp": "1000",
                    "openInterest": "99.000",
                    "singleOpenInterest": "49.500",
                }],
                "nextPageCursor": "",
            },
        }

    rows = collect_bybit_open_interest_history(
        "linear", "ABCUSDT", "1h", 0, 3000, fetcher=fetch, pause_seconds=0,
    )
    assert [row["event_time_ms"] for row in rows] == [1000, 2000]
    assert rows[1]["open_interest"] == "123.4500"
    assert calls[1]["cursor"] == ["cursor-2"]


def test_current_open_interest_snapshots_keep_native_precision():
    binance = collect_binance_open_interest_snapshot(
        "ABCUSDT",
        fetcher=lambda _url: {"symbol": "ABCUSDT", "openInterest": "1234.5600", "time": 1000},
    )
    okx = collect_okx_open_interest_snapshot(
        "ABC-USDT-SWAP",
        fetcher=lambda _url: {
            "code": "0",
            "data": [{
                "instType": "SWAP", "instId": "ABC-USDT-SWAP",
                "oi": "100.1000", "oiCcy": "100.1000", "oiUsd": "500.5000", "ts": "2000",
            }],
        },
    )
    assert binance["open_interest"] == "1234.5600"
    assert okx["open_interest_usd"] == "500.5000"
    assert binance["metric"] == "open_interest_snapshot"


def test_okx_candles_do_not_stop_early_when_server_caps_limit():
    minute = 60_000
    history = [
        [str(i * minute), "1", "1", "1", "1", "1", "1", "1", "1"] for i in range(500)
    ]
    calls = []
    fake = okx_like(history, 0, server_max_limit=100)

    def fetch(url):
        calls.append(url)
        return fake(url)

    rows = collect_okx_history_candles(
        "ABC-USDT", "1m", 0, 500 * minute, limit=300, fetcher=fetch, pause_seconds=0,
    )
    assert len(rows) == 500
    assert rows[0]["event_time_ms"] == 0 and rows[-1]["event_time_ms"] == 499 * minute
    assert len(calls) == 5


def test_binance_klines_continue_after_short_page():
    minute = 60_000
    history = [
        [i * minute, "1", "1", "1", "1", "1", i * minute + 59_999, "1", 1, "1", "1", "0"]
        for i in range(250)
    ]

    def fetch(url):
        params = _query(url)
        start, end = int(params["startTime"]), int(params["endTime"])
        rows = [r for r in history if start <= r[0] <= end]
        return rows[:100]  # server silently caps at 100 even though we ask for 1000

    rows = collect_binance_spot_klines(
        "ABCUSDT", "1m", 0, 250 * minute, limit=1000, fetcher=fetch, pause_seconds=0,
    )
    assert len(rows) == 250


def test_binance_funding_end_is_exclusive():
    history = [
        {"fundingTime": t, "fundingRate": "0.0001"} for t in (1000, 2000, 3000)
    ]
    rows = collect_binance_funding_rates(
        "ABCUSDT", 1000, 3000, fetcher=binance_like(history, "fundingTime"), pause_seconds=0,
    )
    assert [row["event_time_ms"] for row in rows] == [1000, 2000]


def test_bybit_funding_includes_row_exactly_at_start():
    history = [
        {"fundingRateTimestamp": str(t), "fundingRate": "0.0001"} for t in (1000, 2000, 3000)
    ]

    def fetch(url):
        params = _query(url)
        start, end = int(params["startTime"]), int(params["endTime"])
        rows = sorted(
            (r for r in history if start <= int(r["fundingRateTimestamp"]) <= end),
            key=lambda r: -int(r["fundingRateTimestamp"]),
        )[: int(params["limit"])]
        return {"retCode": 0, "result": {"list": rows}}

    rows = collect_bybit_funding_history(
        "linear", "ABCUSDT", 1000, 4000, limit=2, fetcher=fetch, pause_seconds=0,
    )
    assert [row["event_time_ms"] for row in rows] == [1000, 2000, 3000]


def test_in_body_rate_limit_is_retried(monkeypatch):
    import gcie.collectors.public_market as pm

    monkeypatch.setattr(pm.time, "sleep", lambda _s: None)
    responses = iter([
        {"code": "50011", "msg": "Too Many Requests", "data": []},
        {"code": "0", "data": [{"fundingTime": "1000", "fundingRate": "0.0001"}]},
        {"code": "0", "data": []},
    ])
    rows = collect_okx_funding_history(
        "ABC-USDT-SWAP", 0, 2000, fetcher=lambda _url: next(responses), pause_seconds=0,
    )
    assert [row["event_time_ms"] for row in rows] == [1000]
