"""Venue registry for global cross-exchange market-flow research.

This registry describes candidate public data coverage, not guaranteed history.
Adapters must verify endpoint availability and persist source-specific coverage.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VenueSpec:
    venue_id: str
    name: str
    region: str
    jurisdiction_group: str
    market_types: tuple[str, ...]
    data_families: tuple[str, ...]
    tier: int
    notes: str = ""


SPOT_FLOW = ("trades", "candles", "tickers", "orderbook")
DERIVATIVES_FLOW = (
    "open_interest",
    "funding",
    "basis",
    "taker_flow",
    "liquidations",
    "long_short_ratios",
)
WALLET_FLOW = ("wallet_transfers", "exchange_flows", "entity_labels")


VENUES: tuple[VenueSpec, ...] = (
    VenueSpec("upbit", "Upbit", "south_korea", "korean_krw", ("spot",), SPOT_FLOW, 1),
    VenueSpec("bithumb", "Bithumb", "south_korea", "korean_krw", ("spot",), SPOT_FLOW, 1),
    VenueSpec("coinone", "Coinone", "south_korea", "korean_krw", ("spot",), SPOT_FLOW, 2),
    VenueSpec("korbit", "Korbit", "south_korea", "korean_krw", ("spot",), SPOT_FLOW, 2),
    VenueSpec("gopax", "GOPAX", "south_korea", "korean_krw", ("spot",), SPOT_FLOW, 2),
    VenueSpec(
        "binance",
        "Binance",
        "offshore_global",
        "offshore_asia",
        ("spot", "margin", "perpetual", "dated_future"),
        SPOT_FLOW + DERIVATIVES_FLOW + ("borrow_rates",),
        1,
    ),
    VenueSpec(
        "okx",
        "OKX",
        "offshore_global",
        "offshore_asia",
        ("spot", "margin", "perpetual", "dated_future"),
        SPOT_FLOW + DERIVATIVES_FLOW + ("borrow_rates",),
        1,
    ),
    VenueSpec(
        "bybit",
        "Bybit",
        "offshore_global",
        "offshore_asia",
        ("spot", "perpetual", "dated_future"),
        SPOT_FLOW + DERIVATIVES_FLOW,
        1,
    ),
    VenueSpec(
        "htx", "HTX", "offshore_global", "offshore_asia",
        ("spot", "perpetual"), SPOT_FLOW + DERIVATIVES_FLOW, 3,
        "Offshore venue; not a mainland-China domestic exchange.",
    ),
    VenueSpec("gateio", "Gate.io", "offshore_global", "offshore_asia",
              ("spot", "perpetual", "dated_future"), SPOT_FLOW + DERIVATIVES_FLOW, 2),
    VenueSpec("kucoin", "KuCoin", "offshore_global", "offshore_asia",
              ("spot", "perpetual"), SPOT_FLOW + DERIVATIVES_FLOW, 2),
    VenueSpec("bitget", "Bitget", "offshore_global", "offshore_asia",
              ("spot", "perpetual", "dated_future"), SPOT_FLOW + DERIVATIVES_FLOW, 2),
    VenueSpec("mexc", "MEXC", "offshore_global", "offshore_asia",
              ("spot", "perpetual"), SPOT_FLOW + DERIVATIVES_FLOW, 2),
    VenueSpec("bitflyer", "bitFlyer", "japan", "japanese_jpy",
              ("spot", "perpetual"), SPOT_FLOW + ("open_interest",), 2),
    VenueSpec("coincheck", "Coincheck", "japan", "japanese_jpy", ("spot",), SPOT_FLOW, 2),
    VenueSpec("bitbank", "bitbank", "japan", "japanese_jpy", ("spot",), SPOT_FLOW, 2),
    VenueSpec("gmo_coin", "GMO Coin", "japan", "japanese_jpy",
              ("spot", "perpetual"), SPOT_FLOW + ("open_interest",), 2),
    VenueSpec("binance_japan", "Binance Japan", "japan", "japanese_jpy", ("spot",), SPOT_FLOW, 3),
    VenueSpec("coinbase", "Coinbase Exchange", "united_states", "us_usd", ("spot",), SPOT_FLOW, 2),
    VenueSpec("kraken", "Kraken", "united_states", "us_usd",
              ("spot", "margin"), SPOT_FLOW + ("borrow_rates",), 2),
    VenueSpec("gemini", "Gemini", "united_states", "us_usd", ("spot",), SPOT_FLOW, 3),
    VenueSpec("bitstamp", "Bitstamp", "global_usd", "us_accessible_usd", ("spot",), SPOT_FLOW, 3),
    VenueSpec("kraken_futures", "Kraken Futures", "global_derivatives", "offshore_derivatives",
              ("perpetual", "dated_future"), DERIVATIVES_FLOW, 3),
    VenueSpec("deribit", "Deribit", "global_derivatives", "offshore_derivatives",
              ("perpetual", "dated_future", "option"), DERIVATIVES_FLOW, 3),
    VenueSpec("hyperliquid", "Hyperliquid", "global_derivatives", "onchain_derivatives",
              ("perpetual",), DERIVATIVES_FLOW, 2),
    VenueSpec("cme", "CME", "united_states", "regulated_us_futures",
              ("dated_future", "option"), ("open_interest", "trades", "basis"), 3,
              "Regulated futures; keep separate from offshore perpetual swaps."),
)

VENUE_BY_ID = {venue.venue_id: venue for venue in VENUES}


def get_venues(
    *,
    region: str | None = None,
    market_type: str | None = None,
    tier: int | None = None,
) -> tuple[VenueSpec, ...]:
    """Return a stable filtered venue list without implying data completeness."""
    return tuple(
        venue
        for venue in VENUES
        if (region is None or venue.region == region)
        and (market_type is None or market_type in venue.market_types)
        and (tier is None or venue.tier == tier)
    )
