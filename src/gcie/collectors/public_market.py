"""Unauthenticated historical market-data collectors for initial Tier-1 venues.

Functions return normalized observations while preserving venue-native fields.
They do not persist data or imply complete historical availability. Callers should
checkpoint each completed page and persist raw provider payloads separately.
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

JsonFetcher = Callable[[str], Any]


def utc_iso(milliseconds: int) -> str:
    return datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc).isoformat()


def public_json(url: str, *, timeout: int = 20) -> Any:
    """Fetch a public JSON endpoint with a descriptive user agent."""
    request = Request(url, headers={"User-Agent": "GCIE-research/0.1"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _get(fetcher: JsonFetcher, base: str, path: str, params: Mapping[str, Any]) -> Any:
    query = urlencode({key: value for key, value in params.items() if value is not None})
    return fetcher(f"{base}{path}?{query}")


def _interval_ms(interval: str) -> int:
    units = {"m": 60_000, "h": 3_600_000, "d": 86_400_000, "w": 604_800_000}
    try:
        amount, unit = int(interval[:-1]), interval[-1]
        return amount * units[unit]
    except (ValueError, KeyError, IndexError) as exc:
        raise ValueError(f"Unsupported Binance interval: {interval}") from exc


def collect_binance_spot_klines(
    symbol: str, interval: str, start_ms: int, end_ms: int, *,
    limit: int = 1000, fetcher: JsonFetcher = public_json, pause_seconds: float = 0.05,
) -> list[dict[str, Any]]:
    """Backfill Binance spot klines in chronological, non-overlapping pages."""
    if start_ms < 0 or end_ms <= start_ms:
        raise ValueError("Require 0 <= start_ms < end_ms")
    if not 1 <= limit <= 1000:
        raise ValueError("Binance spot kline limit must be between 1 and 1000")
    step = _interval_ms(interval)
    cursor = start_ms
    rows: dict[int, dict[str, Any]] = {}
    while cursor < end_ms:
        payload = _get(fetcher, "https://api.binance.com", "/api/v3/klines", {
            "symbol": symbol.upper(), "interval": interval, "startTime": cursor,
            "endTime": end_ms, "limit": limit,
        })
        if not isinstance(payload, list):
            raise ValueError("Unexpected Binance klines response")
        if not payload:
            break
        page_last = None
        for item in payload:
            if len(item) < 11:
                raise ValueError("Malformed Binance kline row")
            opened = int(item[0])
            if start_ms <= opened < end_ms:
                rows[opened] = {
                    "venue": "binance", "market_type": "spot",
                    "instrument": symbol.upper(), "metric": "ohlcv",
                    "event_time": utc_iso(opened), "event_time_ms": opened,
                    "open": str(item[1]), "high": str(item[2]), "low": str(item[3]),
                    "close": str(item[4]), "volume_base": str(item[5]),
                    "close_time_ms": int(item[6]), "volume_quote": str(item[7]),
                    "trade_count": int(item[8]), "taker_buy_base": str(item[9]),
                    "taker_buy_quote": str(item[10]), "source_endpoint": "/api/v3/klines",
                }
            page_last = opened if page_last is None else max(page_last, opened)
        if page_last is None:
            break
        next_cursor = page_last + step
        if next_cursor <= cursor:
            raise RuntimeError("Binance kline pagination did not advance")
        cursor = next_cursor
        if len(payload) < limit:
            break
        if pause_seconds:
            time.sleep(pause_seconds)
    return [rows[key] for key in sorted(rows)]


def collect_binance_funding_rates(
    symbol: str, start_ms: int, end_ms: int, *,
    limit: int = 1000, fetcher: JsonFetcher = public_json, pause_seconds: float = 0.05,
) -> list[dict[str, Any]]:
    """Collect USDⓈ-M funding history with timestamp pagination."""
    if start_ms < 0 or end_ms <= start_ms:
        raise ValueError("Require 0 <= start_ms < end_ms")
    if not 1 <= limit <= 1000:
        raise ValueError("Binance funding limit must be between 1 and 1000")
    cursor = start_ms
    rows: dict[int, dict[str, Any]] = {}
    while cursor <= end_ms:
        payload = _get(fetcher, "https://fapi.binance.com", "/fapi/v1/fundingRate", {
            "symbol": symbol.upper(), "startTime": cursor, "endTime": end_ms, "limit": limit,
        })
        if not isinstance(payload, list):
            raise ValueError("Unexpected Binance funding response")
        if not payload:
            break
        last_time = None
        for item in payload:
            timestamp = int(item["fundingTime"])
            if start_ms <= timestamp <= end_ms:
                rows[timestamp] = {
                    "venue": "binance", "market_type": "perpetual",
                    "instrument": symbol.upper(), "metric": "funding_rate",
                    "event_time": utc_iso(timestamp), "event_time_ms": timestamp,
                    "funding_rate": str(item["fundingRate"]),
                    "mark_price": str(item.get("markPrice", "")) or None,
                    "source_endpoint": "/fapi/v1/fundingRate",
                }
            last_time = timestamp if last_time is None else max(last_time, timestamp)
        if last_time is None or last_time < cursor:
            raise RuntimeError("Binance funding pagination did not advance")
        if len(payload) < limit:
            break
        cursor = last_time + 1
        if pause_seconds:
            time.sleep(pause_seconds)
    return [rows[key] for key in sorted(rows)]


def collect_okx_history_candles(
    instrument_id: str, bar: str, start_ms: int, end_ms: int, *,
    limit: int = 100, fetcher: JsonFetcher = public_json, pause_seconds: float = 0.12,
) -> list[dict[str, Any]]:
    """Backfill OKX history candles backwards from end_ms using its older-than cursor."""
    if start_ms < 0 or end_ms <= start_ms:
        raise ValueError("Require 0 <= start_ms < end_ms")
    if not 1 <= limit <= 300:
        raise ValueError("OKX history-candles limit must be between 1 and 300")
    cursor = end_ms
    rows: dict[int, dict[str, Any]] = {}
    while cursor > start_ms:
        payload = _get(fetcher, "https://www.okx.com", "/api/v5/market/history-candles", {
            "instId": instrument_id, "bar": bar, "after": cursor, "limit": limit,
        })
        if not isinstance(payload, Mapping) or payload.get("code") != "0":
            raise ValueError(f"Unexpected OKX candle response: {payload!r}")
        data = payload.get("data", [])
        if not data:
            break
        timestamps = []
        for item in data:
            if len(item) < 9:
                raise ValueError("Malformed OKX candle row")
            timestamp = int(item[0])
            timestamps.append(timestamp)
            if start_ms <= timestamp < end_ms:
                rows[timestamp] = {
                    "venue": "okx",
                    "market_type": "perpetual" if instrument_id.endswith("-SWAP") else "spot",
                    "instrument": instrument_id, "metric": "ohlcv",
                    "event_time": utc_iso(timestamp), "event_time_ms": timestamp,
                    "open": str(item[1]), "high": str(item[2]), "low": str(item[3]),
                    "close": str(item[4]), "volume_base": str(item[5]),
                    "volume_quote": str(item[7]), "confirmed": str(item[8]) == "1",
                    "source_endpoint": "/api/v5/market/history-candles",
                }
        oldest = min(timestamps)
        if oldest >= cursor:
            raise RuntimeError("OKX candle pagination did not move backwards")
        cursor = oldest
        if len(data) < limit:
            break
        if pause_seconds:
            time.sleep(pause_seconds)
    return [rows[key] for key in sorted(rows)]


def collect_okx_funding_history(
    instrument_id: str, start_ms: int, end_ms: int, *,
    limit: int = 100, fetcher: JsonFetcher = public_json, pause_seconds: float = 0.2,
) -> list[dict[str, Any]]:
    """Collect OKX perpetual funding history using its older-than cursor."""
    if start_ms < 0 or end_ms <= start_ms:
        raise ValueError("Require 0 <= start_ms < end_ms")
    if not 1 <= limit <= 100:
        raise ValueError("OKX funding-history limit must be between 1 and 100")
    cursor = end_ms
    rows: dict[int, dict[str, Any]] = {}
    while cursor > start_ms:
        payload = _get(fetcher, "https://www.okx.com", "/api/v5/public/funding-rate-history", {
            "instId": instrument_id, "after": cursor, "limit": limit,
        })
        if not isinstance(payload, Mapping) or payload.get("code") != "0":
            raise ValueError(f"Unexpected OKX funding response: {payload!r}")
        data = payload.get("data", [])
        if not data:
            break
        timestamps = []
        for item in data:
            timestamp = int(item["fundingTime"])
            timestamps.append(timestamp)
            if start_ms <= timestamp < end_ms:
                rows[timestamp] = {
                    "venue": "okx", "market_type": "perpetual",
                    "instrument": instrument_id, "metric": "funding_rate",
                    "event_time": utc_iso(timestamp), "event_time_ms": timestamp,
                    "funding_rate": str(item["fundingRate"]),
                    "realized_rate": str(item.get("realizedRate", "")) or None,
                    "source_endpoint": "/api/v5/public/funding-rate-history",
                }
        oldest = min(timestamps)
        if oldest >= cursor:
            raise RuntimeError("OKX funding pagination did not move backwards")
        cursor = oldest
        if len(data) < limit:
            break
        if pause_seconds:
            time.sleep(pause_seconds)
    return [rows[key] for key in sorted(rows)]


def _bybit_result(payload: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping) or payload.get("retCode") != 0:
        raise ValueError(f"Unexpected Bybit {label} response: {payload!r}")
    result = payload.get("result")
    if not isinstance(result, Mapping):
        raise ValueError(f"Malformed Bybit {label} result")
    return result


def collect_bybit_funding_history(
    category: str, symbol: str, start_ms: int, end_ms: int, *,
    limit: int = 200, fetcher: JsonFetcher = public_json, pause_seconds: float = 0.05,
) -> list[dict[str, Any]]:
    """Collect Bybit V5 linear/inverse funding history in bounded time pages.

    Bybit requires startTime and endTime together. The API returns at most
    200 records per request, so a full page is continued from its oldest row.
    """
    if category not in {"linear", "inverse"}:
        raise ValueError("Bybit category must be 'linear' or 'inverse'")
    if start_ms < 0 or end_ms <= start_ms:
        raise ValueError("Require 0 <= start_ms < end_ms")
    if not 1 <= limit <= 200:
        raise ValueError("Bybit funding limit must be between 1 and 200")
    cursor_end = end_ms
    rows: dict[int, dict[str, Any]] = {}
    while cursor_end > start_ms:
        payload = _get(fetcher, "https://api.bybit.com", "/v5/market/funding/history", {
            "category": category, "symbol": symbol.upper(),
            "startTime": start_ms, "endTime": cursor_end, "limit": limit,
        })
        result = _bybit_result(payload, "funding")
        data = result.get("list", [])
        if not data:
            break
        timestamps = []
        for item in data:
            timestamp = int(item["fundingRateTimestamp"])
            timestamps.append(timestamp)
            if start_ms <= timestamp < end_ms:
                rows[timestamp] = {
                    "venue": "bybit", "market_type": "perpetual",
                    "instrument": symbol.upper(), "category": category,
                    "metric": "funding_rate", "event_time": utc_iso(timestamp),
                    "event_time_ms": timestamp, "funding_rate": str(item["fundingRate"]),
                    "source_endpoint": "/v5/market/funding/history",
                }
        oldest = min(timestamps)
        if oldest >= cursor_end:
            raise RuntimeError("Bybit funding pagination did not move backwards")
        if len(data) < limit:
            break
        cursor_end = oldest - 1
        if pause_seconds:
            time.sleep(pause_seconds)
    return [rows[key] for key in sorted(rows)]


def collect_bybit_open_interest_history(
    category: str, symbol: str, interval_time: str, start_ms: int, end_ms: int, *,
    limit: int = 200, fetcher: JsonFetcher = public_json, pause_seconds: float = 0.05,
) -> list[dict[str, Any]]:
    """Collect Bybit V5 historical OI observations using its response cursor."""
    if category not in {"linear", "inverse"}:
        raise ValueError("Bybit category must be 'linear' or 'inverse'")
    if interval_time not in {"5min", "15min", "30min", "1h", "4h", "1d"}:
        raise ValueError("Unsupported Bybit open-interest interval")
    if start_ms < 0 or end_ms <= start_ms:
        raise ValueError("Require 0 <= start_ms < end_ms")
    if not 1 <= limit <= 200:
        raise ValueError("Bybit open-interest limit must be between 1 and 200")
    cursor = None
    seen_cursors: set[str] = set()
    rows: dict[int, dict[str, Any]] = {}
    while True:
        params: dict[str, Any] = {
            "category": category, "symbol": symbol.upper(),
            "intervalTime": interval_time, "startTime": start_ms,
            "endTime": end_ms, "limit": limit,
        }
        if cursor:
            params["cursor"] = cursor
        result = _bybit_result(
            _get(fetcher, "https://api.bybit.com", "/v5/market/open-interest", params),
            "open-interest",
        )
        data = result.get("list", [])
        for item in data:
            timestamp = int(item["timestamp"])
            if start_ms <= timestamp < end_ms:
                rows[timestamp] = {
                    "venue": "bybit", "market_type": "perpetual",
                    "instrument": symbol.upper(), "category": category,
                    "metric": "open_interest", "event_time": utc_iso(timestamp),
                    "event_time_ms": timestamp, "open_interest": str(item["openInterest"]),
                    "single_open_interest": str(item.get("singleOpenInterest", "")) or None,
                    "source_endpoint": "/v5/market/open-interest",
                    "interval": interval_time,
                }
        next_cursor = str(result.get("nextPageCursor") or "")
        if not next_cursor or not data:
            break
        if next_cursor == cursor or next_cursor in seen_cursors:
            raise RuntimeError("Bybit open-interest pagination cursor repeated")
        seen_cursors.add(next_cursor)
        cursor = next_cursor
        if pause_seconds:
            time.sleep(pause_seconds)
    return [rows[key] for key in sorted(rows)]


def collect_binance_open_interest_snapshot(
    symbol: str, *, fetcher: JsonFetcher = public_json,
) -> dict[str, Any]:
    """Collect one current Binance USDⓈ-M open-interest snapshot."""
    payload = _get(fetcher, "https://fapi.binance.com", "/fapi/v1/openInterest", {
        "symbol": symbol.upper(),
    })
    if not isinstance(payload, Mapping) or "openInterest" not in payload:
        raise ValueError(f"Unexpected Binance open-interest response: {payload!r}")
    timestamp = int(payload.get("time", int(time.time() * 1000)))
    return {
        "venue": "binance", "market_type": "perpetual",
        "instrument": symbol.upper(), "metric": "open_interest_snapshot",
        "event_time": utc_iso(timestamp), "event_time_ms": timestamp,
        "open_interest": str(payload["openInterest"]),
        "source_endpoint": "/fapi/v1/openInterest",
    }


def collect_okx_open_interest_snapshot(
    instrument_id: str, *, fetcher: JsonFetcher = public_json,
) -> dict[str, Any]:
    """Collect one current OKX SWAP open-interest snapshot."""
    payload = _get(fetcher, "https://www.okx.com", "/api/v5/public/open-interest", {
        "instType": "SWAP", "instId": instrument_id,
    })
    if not isinstance(payload, Mapping) or payload.get("code") != "0":
        raise ValueError(f"Unexpected OKX open-interest response: {payload!r}")
    data = payload.get("data", [])
    if not data:
        raise ValueError("OKX open-interest response contained no data")
    item = data[0]
    timestamp = int(item["ts"])
    return {
        "venue": "okx", "market_type": "perpetual",
        "instrument": instrument_id, "metric": "open_interest_snapshot",
        "event_time": utc_iso(timestamp), "event_time_ms": timestamp,
        "open_interest": str(item["oi"]),
        "open_interest_coin": str(item.get("oiCcy", "")) or None,
        "open_interest_usd": str(item.get("oiUsd", "")) or None,
        "source_endpoint": "/api/v5/public/open-interest",
    }
