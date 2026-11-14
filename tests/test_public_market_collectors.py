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
        fetcher=lambda _url: [{"fundingTime": 1000, "fundingRate": "0.000125"}],
        pause_seconds=0,
    )
    assert rows[0]["funding_rate"] == "0.000125"
    assert rows[0]["market_type"] == "perpetual"


def test_okx_candles_normalize_quote_volume_and_confirmation():
    payload = {"code": "0", "data": [
        ["1000", "1", "2", "0.5", "1.5", "10", "10", "15", "1"]
    ]}
    rows = collect_okx_history_candles(
        "ABC-USDT", "1m", 0, 2000, fetcher=lambda _url: payload, pause_seconds=0,
    )
    assert rows[0]["volume_quote"] == "15"
    assert rows[0]["confirmed"] is True


def test_okx_funding_history_is_normalized():
    payload = {"code": "0", "data": [
        {"fundingTime": "1000", "fundingRate": "0.0001"}
    ]}
    rows = collect_okx_funding_history(
        "ABC-USDT-SWAP", 0, 2000, fetcher=lambda _url: payload, pause_seconds=0,
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
        if len(calls) == 1:
            rows = [
                {"fundingRateTimestamp": "3000", "fundingRate": "0.00012300"},
                {"fundingRateTimestamp": "2000", "fundingRate": "-0.00004000"},
            ]
        else:
            rows = [{"fundingRateTimestamp": "1000", "fundingRate": "0.00001000"}]
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
                        {"timestamp": "2000", "openInterest": "123.4500", "singleOpenInterest": "61.7250"}
                    ],
                    "nextPageCursor": "cursor-2",
                },
            }
        return {
            "retCode": 0,
            "result": {
                "list": [{"timestamp": "1000", "openInterest": "99.000", "singleOpenInterest": "49.500"}],
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
