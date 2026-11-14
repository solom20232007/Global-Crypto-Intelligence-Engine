from gcie.collectors.public_market import (
    collect_binance_funding_rates, collect_binance_spot_klines,
    collect_okx_funding_history, collect_okx_history_candles,
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
